# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
"""GigaAM (Sber) on Modal GPU — a Russian-specific engine.

Included precisely because it may split the two things this benchmark measures.
A model trained hard on Russian should do well on the Russian matrix of the
speech and may do badly on the Latin-script IT terminology embedded in it. If
that happens it is a finding, not a disappointment: it is direct evidence that
overall WER and terminology recognition are different questions, which is the
argument the whole metric design rests on.

Same fairness contract as every other engine: frozen segment bytes, 16 kHz
asserted rather than corrected, no preprocessing of our own.

Run:
    modal run task2-stt-benchmark/modal_app/gigaam_engine.py::smoke
    modal run task2-stt-benchmark/modal_app/gigaam_engine.py::run_corpus
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
        "torch==2.5.1", "gigaam[longform]", "soundfile==0.12.1", "numpy<2"
    )
)

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name(
    "explee-stt-benchmark-models", create_if_missing=True
)
CACHE = "/models"


@app.cls(
    image=image,
    gpu="L4",
    volumes={CACHE: model_cache},
    timeout=60 * 40,
    scaledown_window=120,
    max_containers=1,
)
class GigaAM:
    model_key: str = modal.parameter(default="v2_rnnt")

    @modal.enter()
    def load(self):
        import os

        os.environ.setdefault("HF_HOME", CACHE)
        os.environ.setdefault("GIGAAM_CACHE_DIR", CACHE)
        import gigaam

        started = time.monotonic()
        self.model = gigaam.load_model(self.model_key)
        self.model_id = f"salute-developers/GigaAM:{self.model_key}"
        self.load_s = round(time.monotonic() - started, 3)

    @modal.method()
    def transcribe(self, segment_id: str, audio: bytes, tuned: bool = False) -> dict:
        import tempfile

        import soundfile as sf

        started = time.monotonic()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as handle:
            handle.write(audio)
            handle.flush()
            info = sf.info(handle.name)
            if info.samplerate != 16_000:
                raise ValueError(
                    f"{segment_id} is {info.samplerate} Hz; the corpus is 16 kHz"
                )
            # Our frozen segments are exactly 30.000 s and GigaAM's short-form
            # API refuses anything at or above 30 s. Trimming them for this one
            # engine would break the identical-input rule, so we use the vendor's
            # own long-form path — the engine's internal segmentation is part of
            # the engine, unlike preprocessing we would have applied ourselves.
            try:
                output = self.model.transcribe(handle.name)
            except ValueError:
                output = self.model.transcribe_longform(handle.name)

        first = output
        while isinstance(first, (list, tuple)) and first:
            first = first[0]
        text = first if isinstance(first, str) else (getattr(first, "text", "") or "")

        return {
            "segment_id": segment_id,
            "model_key": f"gigaam-{self.model_key}",
            "model_id": self.model_id,
            "track": "tuned" if tuned else "default",
            "text": text,
            "offsets": [],
            "raw": json.dumps(str(output), ensure_ascii=False),
            "inference_s": round(time.monotonic() - started, 3),
            "container_load_s": self.load_s,
            "torch_dtype": "float32",
            "gpu": "L4",
        }


def _segments(manifest_path: str) -> list:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["segments"]


@app.local_entrypoint()
def smoke(manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json"):
    segment = _segments(manifest)[0]
    engine = GigaAM()
    result = engine.transcribe.remote(
        segment["id"], Path(segment["path"]).read_bytes()
    )
    print(f"{result['model_id']}  load {result['container_load_s']}s  "
          f"infer {result['inference_s']}s")
    print("text:", repr(result["text"])[:300])


@app.local_entrypoint()
def run_corpus(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    out_dir: str = "task2-stt-benchmark/data/raw",
):
    segments = _segments(manifest)
    engine = GigaAM()
    target = Path(out_dir) / "gigaam-v2_rnnt-default"
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

    print(f"gigaam: {done}/{len(segments)} segments in "
          f"{time.monotonic() - started:.1f}s")
    for failure in failures[:5]:
        print("  failure:", failure)
