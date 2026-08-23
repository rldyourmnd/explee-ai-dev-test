# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportArgumentType=false
#
# These four rules only. torch, librosa, transformers, soundfile, nemo and
# gigaam exist inside the Modal container image and are deliberately not
# installed locally, so pyright cannot resolve them or the types that flow
# from them. Modal's decorators are also beyond it: `.remote` and `.starmap`
# are attached at runtime, and `modal.parameter` class fields are not visible
# as constructor arguments. Every OTHER rule stays active on this file, which
# is the point: the directory used to be excluded wholesale, so a new defect
# of any kind landed here unseen.
"""Qwen3-ASR and GigaAM-v3 on Modal GPU — the two engines the brief named.

Both are worth a slot for the same reason: each is a plausible challenger to
Whisper on exactly this speech. Qwen3-ASR-1.7B is reported as the strongest
open ASR model; GigaAM-v3 is Russian-specialised and its authors report beating
Whisper large-v3 on Russian. If either wins, the recommendation changes — which
is the only test worth spending GPU time on.

They share an image because both need a newer `transformers` than the Whisper
app pins, and building one image instead of two is the cheaper way to find out.

Same fairness contract as every other engine: frozen segment bytes, 16 kHz
asserted rather than corrected, no trimming and no preprocessing of our own.
"""
# No `from __future__ import annotations`: Modal reads `modal.parameter` types
# at class-construction time and cannot resolve a string annotation.
import json
import time
from pathlib import Path

import modal

APP_NAME = "explee-stt-benchmark"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "torch==2.5.1",
        # Qwen3-ASR needs native support, which landed in transformers 5.13.
        "transformers>=5.13.0",
        "accelerate",
        "librosa==0.10.2.post1",
        "soundfile==0.12.1",
    )
)

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name(
    "explee-stt-benchmark-models", create_if_missing=True
)
CACHE = "/models"

MODELS = {
    "qwen3-asr-1.7b": "Qwen/Qwen3-ASR-1.7B",
    "gigaam-v3": "ai-sage/GigaAM-v3",
}


@app.cls(
    image=image,
    # Fan-out capped at 4 of the workspace's 10 GPUs. The corpus is one hour in
    # 30 s pieces and a single L4 clears it in ten to twenty minutes, so ten
    # containers buy no meaningful wall-clock and simply occupy the whole quota
    # — which is exactly what happened. Engines run sequentially, so the
    # benchmark never holds more than four GPUs.
    gpu=["L4", "A10"],        # smallest that fits; fallback so a busy type cannot stall
    scaledown_window=60,      # release GPUs promptly between engines
    volumes={CACHE: model_cache},
    timeout=60 * 40,
    max_containers=4,
)
class Challenger:
    model_key: str = modal.parameter(default="qwen3-asr-1.7b")

    @modal.enter()
    def load(self):
        import os

        os.environ.setdefault("HF_HOME", CACHE)
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        self.model_id = MODELS[self.model_key]
        started = time.monotonic()
        self.processor = AutoProcessor.from_pretrained(
            self.model_id, cache_dir=CACHE, trust_remote_code=True
        )
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_id, cache_dir=CACHE, torch_dtype=torch.float16,
            trust_remote_code=True,
        ).to("cuda")
        self.model.eval()
        self.load_s = round(time.monotonic() - started, 3)

    @modal.method()
    def transcribe(self, segment_id: str, audio: bytes, tuned: bool = False) -> dict:
        import io

        import librosa
        import torch

        started = time.monotonic()
        samples, sr = librosa.load(io.BytesIO(audio), sr=None, mono=True)
        if sr != 16_000:
            raise ValueError(f"{segment_id} is {sr} Hz; the frozen corpus is 16 kHz")

        # Qwen3-ASR's encoder requires the feature length to be a multiple of
        # 100 frames, and a 30.000 s segment lands on 2997. We pad with trailing
        # SILENCE to the next multiple. This is materially different from the
        # trim we refused for GigaAM: padding adds no speech and removes none,
        # so no engine sees less audio than another. The padding is recorded on
        # every result rather than left implicit.
        frame = 160                       # 10 ms hop at 16 kHz
        block = 100 * frame               # the encoder's required multiple
        pad = (-len(samples)) % block
        if pad:
            import numpy as np

            samples = np.concatenate([samples, np.zeros(pad, dtype=samples.dtype)])

        # Qwen3-ASR is an audio-LLM: its processor wants a chat-templated text
        # prompt alongside the audio, unlike Whisper's audio-only processor.
        conversation = [{
            "role": "user",
            "content": [
                {"type": "audio", "audio": samples},
                {"type": "text", "text": "Transcribe the Russian speech verbatim."},
            ],
        }]
        prompt = self.processor.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=prompt, audio=[samples], sampling_rate=sr, return_tensors="pt"
        ).to("cuda")
        # The model is fp16 but the processor emits fp32 audio features and the
        # first conv layer refuses the mismatch. Cast ONLY the feature tensor:
        # casting every float tensor also hits the length/mask tensors, and
        # halving those loses the integer precision the encoder checks audio
        # tokens against ("features and audio tokens do not match").
        for key in ("input_features", "input_values"):
            value = inputs.get(key)
            if value is not None and value.dtype == torch.float32:
                inputs[key] = value.half()
        with torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=440)
        # Strip the echoed prompt: decoding the full sequence would score the
        # instruction itself as transcribed speech.
        trimmed = generated[:, inputs["input_ids"].shape[1]:]
        text = self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]

        return {
            "segment_id": segment_id,
            "model_key": self.model_key,
            "model_id": self.model_id,
            "track": "tuned" if tuned else "default",
            "text": text,
            "offsets": [],
            "raw": json.dumps({"text": text}, ensure_ascii=False),
            "inference_s": round(time.monotonic() - started, 3),
            "container_load_s": self.load_s,
            "torch_dtype": "float16",
            # The GPU actually allocated, not the one requested: the fallback
            # list can hand back A10 instead of L4 and the operational table
            # must report what ran, not what we asked for.
            "gpu": torch.cuda.get_device_name(0),
            "cold_start_s": self.load_s,
            "input_padding_samples": int(pad),
        }


def _segments(manifest_path: str) -> list:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["segments"]


@app.local_entrypoint()
def smoke(
    manifest: str = "task2-stt-benchmark/data/manifest-hlk8s.json",
    model_key: str = "qwen3-asr-1.7b",
):
    segment = _segments(manifest)[0]
    engine = Challenger(model_key=model_key)
    result = engine.transcribe.remote(
        segment["id"], Path(segment["path"]).read_bytes()
    )
    print(f"{result['model_id']}  load {result['container_load_s']}s  "
          f"infer {result['inference_s']}s")
    print("text:", repr(result["text"])[:300])


@app.local_entrypoint()
def run_corpus(
    manifest: str = "task2-stt-benchmark/data/manifest-hlk8s.json",
    model_key: str = "qwen3-asr-1.7b",
    out_dir: str = "task2-stt-benchmark/data/raw-hlk8s",
):
    segments = _segments(manifest)
    engine = Challenger(model_key=model_key)
    target = Path(out_dir) / f"{model_key}-default"
    target.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    payloads = [(s["id"], Path(s["path"]).read_bytes(), False) for s in segments]
    done, failures = 0, []
    for result in engine.transcribe.starmap(payloads, return_exceptions=True):
        if isinstance(result, Exception):
            failures.append(str(result)[:200])
            continue
        (target / f"{result['segment_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        done += 1

    print(f"{model_key}: {done}/{len(segments)} segments in "
          f"{time.monotonic() - started:.1f}s")
    for failure in failures[:5]:
        print("  failure:", failure)
