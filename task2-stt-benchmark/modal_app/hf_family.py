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
"""Two more open ASR architectures on Modal GPU.

Added to reach the >=5 engines the task requires, after Canary and GigaAM were
blocked for reasons specific to them. Both are chosen to avoid those blockers:
open weights, no gated dependency, no 30-second input ceiling.

* `seamless-m4t-v2-large` — Meta's multilingual speech model, a different
  architecture from both Whisper and NeMo's Parakeet.
* `wav2vec2-xlsr-ru` — a Russian CTC fine-tune. Small, ungated, and useful
  precisely because a Russian-specialised model is expected to handle the
  Russian matrix well and the embedded English terminology badly. Either
  outcome is informative.

Same fairness contract as every other engine: frozen segment bytes in,
transcribed as given, 16 kHz asserted rather than corrected, no trimming and no
preprocessing of our own.

Run:
    modal run task2-stt-benchmark/modal_app/hf_family.py::smoke --model-key seamless-m4t-v2
    modal run task2-stt-benchmark/modal_app/hf_family.py::run_corpus --model-key wav2vec2-xlsr-ru
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
        "transformers==4.46.3",
        "sentencepiece==0.2.0",
        "accelerate==1.1.1",
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
    "seamless-m4t-v2": "facebook/seamless-m4t-v2-large",
    "wav2vec2-xlsr-ru": "jonatasgrosman/wav2vec2-large-xlsr-53-russian",
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
    # Serialised: several containers racing to populate the shared model volume
    # is what broke the first NeMo run, and a few minutes is cheaper than a
    # flaky engine result.
    max_containers=4,
)
class HFEngine:
    model_key: str = modal.parameter(default="seamless-m4t-v2")

    @modal.enter()
    def load(self):
        import torch

        self.model_id = MODELS[self.model_key]
        self.is_seamless = self.model_key.startswith("seamless")
        started = time.monotonic()
        if self.is_seamless:
            from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToText

            self.processor = AutoProcessor.from_pretrained(
                self.model_id, cache_dir=CACHE
            )
            self.model = SeamlessM4Tv2ForSpeechToText.from_pretrained(
                self.model_id, cache_dir=CACHE, torch_dtype=torch.float16
            ).to("cuda")
        else:
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            self.processor = Wav2Vec2Processor.from_pretrained(
                self.model_id, cache_dir=CACHE
            )
            self.model = Wav2Vec2ForCTC.from_pretrained(
                self.model_id, cache_dir=CACHE
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

        if self.is_seamless:
            inputs = self.processor(
                audios=samples, sampling_rate=sr, return_tensors="pt"
            ).to("cuda", torch.float16)
            with torch.no_grad():
                generated = self.model.generate(**inputs, tgt_lang="rus")
            text = self.processor.batch_decode(
                generated, skip_special_tokens=True
            )[0]
        else:
            inputs = self.processor(
                samples, sampling_rate=sr, return_tensors="pt", padding=True
            )
            with torch.no_grad():
                logits = self.model(inputs.input_values.to("cuda")).logits
            predicted = torch.argmax(logits, dim=-1)
            text = self.processor.batch_decode(predicted)[0]

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
            "torch_dtype": "float16" if self.is_seamless else "float32",
            "gpu": "L4",
        }


def _segments(manifest_path: str) -> list:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["segments"]


@app.local_entrypoint()
def smoke(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "seamless-m4t-v2",
):
    segment = _segments(manifest)[0]
    engine = HFEngine(model_key=model_key)
    result = engine.transcribe.remote(
        segment["id"], Path(segment["path"]).read_bytes()
    )
    print(f"{result['model_id']}  load {result['container_load_s']}s  "
          f"infer {result['inference_s']}s")
    print("text:", repr(result["text"])[:300])


@app.local_entrypoint()
def run_corpus(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "seamless-m4t-v2",
    out_dir: str = "task2-stt-benchmark/data/raw",
):
    segments = _segments(manifest)
    engine = HFEngine(model_key=model_key)
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
