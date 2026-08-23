# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
"""Whisper-family engines on Modal GPU, full precision.

App name `explee-stt-benchmark`, scoped to itself. The workspace is never
enumerated — it holds unrelated deployments whose names must not reach a trace
that ships verbatim.

Why full precision: an 8 GB laptop forced a quantised build, and a quantised
local model losing to a cloud engine would be a confounded result. On GPU the
comparison is between models, not between memory budgets.

Fairness: the class receives frozen segment bytes and transcribes them as
given. It does not resample, denoise, re-cut or VAD-segment; every engine sees
byte-identical input (`PREREGISTRATION.md` §7). The 16 kHz rate is asserted,
not corrected, so a corpus that stopped matching the manifest fails loudly.

The model loads once per container (`modal.enter`) rather than once per
segment, because 120 reloads of a 3 GB model would be most of the GPU bill.

Run:
    modal run task2-stt-benchmark/modal_app/whisper_family.py::smoke
    modal run task2-stt-benchmark/modal_app/whisper_family.py::run_corpus \\
        --model-key whisper-large-v3
"""
# No `from __future__ import annotations` here on purpose: Modal resolves
# `modal.parameter` types at class-construction time and cannot read a string
# annotation, so postponed evaluation breaks the class parameter outright.
import json
import time
from pathlib import Path

import modal

APP_NAME = "explee-stt-benchmark"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.5.1",
        "transformers==4.46.3",
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
    "whisper-large-v3": "openai/whisper-large-v3",
    "whisper-large-v3-turbo": "openai/whisper-large-v3-turbo",
}

#: Tuned-track hint. Whisper accepts a text prompt that biases decoding; it is
#: the same frozen glossary every vendor's terminology feature receives, and it
#: is never applied on the default track.
TUNED_PROMPT = (
    "RAG, ClickHouse, Kafka, Kubernetes, Docker, Postgres, Redis, Grafana, "
    "Prometheus, Airflow, Terraform, Cloudflare Worker, S3, Elasticsearch, "
    "OpenSearch, pgvector, Qdrant, LangChain, OpenAI, Anthropic, Deepgram, "
    "ElevenLabs, Speechmatics, Whisper, Azure, GCP, AWS, LLM, API, SDK, GPU, "
    "CI/CD, SLA, embedding, prompt, fine-tuning, latency, throughput, deploy, "
    "rollback, pipeline, chunking, reranker, feature store, webhook, endpoint, "
    "backfill, staging, prod"
)


@app.cls(
    image=image,
    gpu="L4",
    volumes={CACHE: model_cache},
    timeout=60 * 30,
    scaledown_window=120,
    max_containers=10,
)
class Whisper:
    model_key: str = modal.parameter(default="whisper-large-v3")

    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        self.model_id = MODELS[self.model_key]
        started = time.monotonic()
        self.processor = AutoProcessor.from_pretrained(self.model_id, cache_dir=CACHE)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_id,
            cache_dir=CACHE,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
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

        features = self.processor(
            samples, sampling_rate=sr, return_tensors="pt", return_attention_mask=True
        )
        inputs = features.input_features.to("cuda", torch.float16)
        generate_kwargs = {
            "language": "ru",
            "task": "transcribe",
            "return_timestamps": True,
            "attention_mask": features.attention_mask.to("cuda"),
        }
        if tuned:
            generate_kwargs["prompt_ids"] = self.processor.get_prompt_ids(
                TUNED_PROMPT, return_tensors="pt"
            ).to("cuda")

        with torch.no_grad():
            generated = self.model.generate(inputs, **generate_kwargs)
        decoded = self.processor.batch_decode(
            generated, skip_special_tokens=True, output_offsets=True
        )
        elapsed = round(time.monotonic() - started, 3)

        text = decoded[0]["text"] if decoded else ""
        if tuned and text.startswith(TUNED_PROMPT[:40]):
            # Whisper sometimes echoes the prompt into the transcript. Left in
            # place would score as a huge hallucination for the tuned track and
            # a fake advantage for the default one, so it is stripped here and
            # the strip is recorded on the result.
            text = text[len(TUNED_PROMPT):].lstrip(" .,")

        return {
            "segment_id": segment_id,
            "model_key": self.model_key,
            "model_id": self.model_id,
            "track": "tuned" if tuned else "default",
            "text": text,
            "offsets": [
                {"text": o.get("text", ""), "timestamp": list(o.get("timestamp", ()))}
                for o in (decoded[0].get("offsets", []) if decoded else [])
            ],
            "raw": json.dumps(decoded, ensure_ascii=False, default=str),
            "inference_s": elapsed,
            "container_load_s": self.load_s,
            "torch_dtype": "float16",
            "gpu": "L4",
        }


def _segments(manifest_path: str) -> list[dict]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["segments"]


@app.local_entrypoint()
def smoke(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "whisper-large-v3",
):
    """One segment, to prove the path before spending GPU minutes on 120."""
    segment = _segments(manifest)[0]
    engine = Whisper(model_key=model_key)
    result = engine.transcribe.remote(
        segment["id"], Path(segment["path"]).read_bytes()
    )
    print(f"{result['model_id']}  load {result['container_load_s']}s  "
          f"infer {result['inference_s']}s")
    print(result["text"][:300])


@app.local_entrypoint()
def run_corpus(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "whisper-large-v3",
    tuned: str = "false",
    out_dir: str = "task2-stt-benchmark/data/raw",
):
    """Transcribe every frozen segment and store raw output locally.

    Raw first: each response is written to disk before anything reads it, so
    the report can publish a hash of what the model actually returned rather
    than of what the scorer decided it meant.
    """
    is_tuned = tuned.lower() in ("1", "true", "yes")
    segments = _segments(manifest)
    engine = Whisper(model_key=model_key)
    track = "tuned" if is_tuned else "default"
    target = Path(out_dir) / f"{model_key}-{track}"
    target.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    payloads = [
        (s["id"], Path(s["path"]).read_bytes(), is_tuned) for s in segments
    ]
    done = 0
    failures: list[str] = []
    for result in engine.transcribe.starmap(payloads, return_exceptions=True):
        if isinstance(result, Exception):
            failures.append(str(result)[:200])
            continue
        (target / f"{result['segment_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        done += 1

    elapsed = time.monotonic() - started
    print(f"{model_key}/{track}: {done}/{len(segments)} segments in {elapsed:.1f}s")
    if failures:
        print(f"failures: {len(failures)}")
        for failure in failures[:5]:
            print("  ", failure)
