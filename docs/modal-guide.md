# Running the Task 2 engines on Modal — current API and the GPU cap

**Status: COMPLETE — historical.** How the Task 2 engines were run, written while that work was live. The benchmark is published; kept for reproducibility, not as a live runbook.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


The workspace hit its plan limit of **10 concurrent GPUs**, with a `Whisper.*`
function holding all ten. This is not a capacity problem. It is a fan-out set
higher than the work needs, and the fix costs nothing in wall-clock.

## The arithmetic first

The corpus is 120 segments of 30 s — one hour of audio. Whisper large-v3 on a
single L4 or A10 transcribes a 30 s segment in a few seconds, so **one** GPU
clears the whole corpus in roughly ten to twenty minutes. Four containers finish
it in under five. Ten containers do not make it meaningfully faster; they just
occupy the entire workspace quota so nothing else can start.

Run the engines **sequentially**, a few containers each. Five engines at four
containers apiece, one engine at a time, never exceeds four of the ten GPUs and
leaves the workspace usable.

## Current API — these are the parameter names as of now

Scaling is controlled on the function decorator:

```python
@app.function(
    gpu="L4",                 # see the type list below
    max_containers=4,         # HARD CAP on concurrent containers → GPUs
    scaledown_window=60,      # seconds a container may sit idle before release
    timeout=600,
)
def transcribe(segment: bytes) -> dict:
    ...
```

- `max_containers` — the upper limit on containers for this function. **This is
  the parameter that solves the quota problem.**
- `min_containers` — containers kept warm while the function is idle. Leave at 0
  for a benchmark; warm containers hold GPUs you are not using.
- `buffer_containers` — extra containers kept ready while active. Leave unset.
- `scaledown_window` — how long an idle container survives before release. Keep
  it short so GPUs return to the pool between engines.

The older names `concurrency_limit` and `container_idle_timeout` no longer appear
in the documentation; use `max_containers` and `scaledown_window`.

## GPU selection

```python
@app.function(gpu="L4")            # single GPU
@app.function(gpu="H100:2")        # two on one machine
@app.function(gpu=["L4", "A10"])   # fallback order — first available wins
```

Available types: `T4`, `L4`, `A10`, `L40S`, `A100` / `A100-40GB` / `A100-80GB`,
`H100` / `H100!`, `H200`, `B200` / `B200+`, `B300`, `RTX-PRO-6000`.

Per-container maxima: up to 8 GPUs for T4, L4, L40S, A100, H100, H200, B200,
B300; up to 4 for A10. Asking for more than two lengthens scheduling waits.

**Pick the smallest GPU that fits the model.** Whisper large-v3 needs roughly
10 GB in fp16, so `L4` (24 GB) or `A10` (24 GB) is right; an H100 costs several
times more per hour and finishes a 30 s clip no sooner in any way that matters
here. Parakeet and GigaAM are smaller still — `T4` or `L4`. Use the fallback list
so a busy GPU type does not stall the run.

## Input concurrency is the wrong tool here

`@modal.concurrent(max_inputs=N)` runs several inputs inside one container. It is
built for I/O-bound work — database queries, external API calls — and for GPU
serving frameworks that do continuous batching, such as vLLM. Straight ASR
inference is GPU-bound: stacking inputs in one container contends for the same
device and slows everything down. Scale with containers, not with input
concurrency, and only reach for `@modal.concurrent` if a specific engine ships a
batching server.

## Practical shape for the benchmark

```python
import modal

image = (
    modal.Image.debian_slim()
    .pip_install("faster-whisper==...", "ctranslate2==...")   # pin exact versions
)
app = modal.App("explee-stt-benchmark")                        # named, never enumerate the workspace

@app.function(image=image, gpu=["L4", "A10"], max_containers=4,
              scaledown_window=60, timeout=900)
def transcribe_whisper(segment_bytes: bytes, segment_id: str) -> dict:
    ...   # return raw output plus timings; persist raw before parsing
```

Drive it with `.map()` over the 120 segments; `max_containers` caps the fan-out
regardless of how many inputs you submit.

Between engines, let containers scale down before starting the next one, so GPUs
are actually released rather than merely idle.

## Recording what a benchmark has to record

Pin the image and every library version — a benchmark whose environment is not
reproducible is an anecdote. Capture the resolved model revision, the GPU type
actually allocated (which can differ from the first choice when a fallback list
is used), and end-to-end wall time including cold start, separately from pure
inference time. Cold start is a real production cost and belongs in the
operational table.

Persist the raw output, `fsync`, hash it, and only then parse.

## Two workspace rules

**Never run `modal app list` or anything that enumerates the workspace.** It
prints apps belonging to unrelated client projects, and this session's trace is
published verbatim to a third party. Scope every command to the app you created
and named for this benchmark. This is the same class of leak that destroyed the
first Task 3 trace and that the `--list` defect caused in the exporter — three
occurrences now, always from a listing command reaching past the project.

**Stop the app when the run finishes** so no GPU is held after the benchmark.
