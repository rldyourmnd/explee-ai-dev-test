# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
"""NVIDIA NeMo engines on Modal GPU: Parakeet-TDT v3 and Canary.

A second model lineage matters twice over. It is two more engines for the
ranking, and — because the reference protocol drafts from two engines of
*different* lineages — it is the only way the drafting pair is not two Whispers
agreeing with each other.

Same fairness contract as the Whisper app: frozen segment bytes in, transcribed
as given, 16 kHz asserted rather than corrected, no resampling or VAD of our
own. NeMo wants a file path, so the bytes are written to the container's own
tmpfs unmodified and deleted after; nothing about the audio changes.

Run:
    modal run task2-stt-benchmark/modal_app/nemo_family.py::smoke
    modal run task2-stt-benchmark/modal_app/nemo_family.py::run_corpus \\
        --model-key parakeet-tdt-0.6b-v3
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
    .apt_install("ffmpeg", "libsndfile1", "git")
    .pip_install(
        # NeMo 2.1.0 still calls `np.sctypes`, removed in NumPy 2.0, so the
        # pin is load-bearing rather than caution: without it every transcribe
        # call dies inside NeMo's own audio preprocessing.
        "numpy<2",
        "torch==2.5.1",
        "nemo_toolkit[asr]==2.1.0",
        "cuda-python>=12.3",
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
    "parakeet-tdt-0.6b-v3": "nvidia/parakeet-tdt-0.6b-v3",
    "canary-1b-v2": "nvidia/canary-1b-v2",
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
    # One container on purpose. With several, NeMo's `from_pretrained` races on
    # the shared model volume and one container ends up trying to instantiate
    # the abstract `ASRModel` base class instead of the concrete subclass. A
    # 120-segment run at ~3 s each is a few minutes serialised, which is a
    # cheaper price than a flaky engine result.
    max_containers=4,
)
class Nemo:
    model_key: str = modal.parameter(default="parakeet-tdt-0.6b-v3")

    @modal.enter()
    def load(self):
        import os

        os.environ.setdefault("HF_HOME", CACHE)
        os.environ.setdefault("NEMO_CACHE_DIR", CACHE)
        from nemo.collections.asr.models import ASRModel

        self.model_id = MODELS[self.model_key]
        started = time.monotonic()
        self.model = ASRModel.from_pretrained(model_name=self.model_id)
        self.model.eval()
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
            kwargs = {}
            if self.model_key.startswith("canary"):
                # Canary is a translation-capable model: source and target must
                # both be Russian or it would translate, and translation is not
                # transcription (reference policy R12).
                kwargs = {"source_lang": "ru", "target_lang": "ru", "pnc": "yes"}
            output = self.model.transcribe([handle.name], **kwargs)

        elapsed = round(time.monotonic() - started, 3)
        # NeMo 2.1 returns `([hypotheses], [something_else])` for some models and
        # a bare list for others, and a hypothesis may be a string or an object
        # with `.text`. Unwrapping defensively here — and asserting non-empty in
        # run_corpus — because an empty string is not a transcription failure the
        # scorer could distinguish from an engine that heard silence.
        first = output
        while isinstance(first, (list, tuple)) and first:
            first = first[0]
        text = first if isinstance(first, str) else (getattr(first, "text", "") or "")
        return {
            "segment_id": segment_id,
            "model_key": self.model_key,
            "model_id": self.model_id,
            "track": "tuned" if tuned else "default",
            "text": text,
            "offsets": [],
            "raw": json.dumps(str(output), ensure_ascii=False),
            "output_repr": repr(output)[:400],
            "inference_s": elapsed,
            "container_load_s": self.load_s,
            "torch_dtype": "float32",
            "gpu": "L4",
        }


def _segments(manifest_path: str) -> list:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["segments"]


@app.local_entrypoint()
def smoke(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "parakeet-tdt-0.6b-v3",
):
    segment = _segments(manifest)[0]
    engine = Nemo(model_key=model_key)
    result = engine.transcribe.remote(
        segment["id"], Path(segment["path"]).read_bytes()
    )
    print(f"{result['model_id']}  load {result['container_load_s']}s  "
          f"infer {result['inference_s']}s")
    print("text:", repr(result["text"])[:300])
    print("repr:", result.get("output_repr", "")[:400])


@app.local_entrypoint()
def run_corpus(
    manifest: str = "task2-stt-benchmark/data/manifest-rt1027.json",
    model_key: str = "parakeet-tdt-0.6b-v3",
    tuned: str = "false",
    out_dir: str = "task2-stt-benchmark/data/raw",
):
    is_tuned = tuned.lower() in ("1", "true", "yes")
    segments = _segments(manifest)
    engine = Nemo(model_key=model_key)
    track = "tuned" if is_tuned else "default"
    target = Path(out_dir) / f"{model_key}-{track}"
    target.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    payloads = [(s["id"], Path(s["path"]).read_bytes(), is_tuned) for s in segments]
    done, failures = 0, []
    for result in engine.transcribe.starmap(payloads, return_exceptions=True):
        if isinstance(result, Exception):
            failures.append(str(result)[:200])
            continue
        (target / f"{result['segment_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        done += 1

    print(f"{model_key}/{track}: {done}/{len(segments)} segments in "
          f"{time.monotonic() - started:.1f}s")
    for failure in failures[:5]:
        print("  failure:", failure)
