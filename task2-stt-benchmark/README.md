# Task 2 — STT benchmark for Russian speech with English IT terminology

Choosing a transcriber for meetings where the engine currently hears `РАКа` for
RAG and `Lead House` for ClickHouse. Designing the evaluation is the task, so
the evaluation is built and frozen first, before any engine output exists.

## Order of work, and why it is this order

The eval was designed, implemented, tested and committed **before** a corpus was
chosen and before any engine was called. That is not a workaround for waiting on
decisions — it is the only order in which the numbers mean anything. A metric
built after seeing engine output can be tuned, however unconsciously, to favour
a result. The freeze timestamps are in `PREREGISTRATION.md` and in git history.

## What is frozen

| Artefact | What it fixes |
|---|---|
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | primary metric, guardrail, tie-break order, statistics, slate, falsification conditions |
| [`docs/reference-policy.md`](docs/reference-policy.md) | how the gold transcript is written — 12 rules, each with a worked pass and fail |
| [`glossary.json`](glossary.json) | the 50 IT terms whose recognition is measured; not extended after hearing output |
| `tests/test_task2_*.py` | 44 tests, including the employer's own two failures asserted to score as failures |

## The harness

```
harness/
  manifest.py   freeze one source file: SHA-256, probe, uniform cuts, per-segment hash
  adapters/     one interface per engine; a missing key skips one adapter, not the run
  runner.py     identical retry policy, raw-output storage, failure accounting, results CSV
  normalize.py  scoring normalisation (shallow) and term normalisation (stem-folding)
  align.py      one exact Levenshtein alignment per segment, shared by every metric
  metrics.py    counts, not ratios — WER, CER, code-switch WER, term P/R/F1, name recall,
                Latin-to-Cyrillic rate, hallucination, omission, boundary errors,
                speaker attribution, timestamp quality
  bootstrap.py  paired bootstrap over segments, and the pre-declared decision rule
```

Stdlib only, matching the rest of this repository. `ffmpeg`/`ffprobe` are
required to cut the corpus and their absence is a hard error, never a silent
fallback to a different decoder.

Three properties the tests enforce, because each is a way a benchmark can lie:

* **Unmeasured is not zero.** An engine returning no timings scores `None` for
  timestamp quality, not a perfect `0.0`.
* **Silence is not a good answer.** An empty transcript scores WER `1.0` and
  term recall `0.0`; a failed segment is dropped from *both* engines in a paired
  comparison rather than imputed.
* **A term counts only where it was spoken.** Saying `ClickHouse` thirty words
  later earns no recall credit and costs precision.

## Status

| Item | State |
|---|---|
| Eval design frozen | done — `PREREGISTRATION.md` |
| Reference policy frozen | done — 12 rules with worked examples |
| Glossary frozen | done — 50 terms, hashed |
| Metrics + tests | done — see `tests/test_task2_*.py` |
| Paired bootstrap + decision rule | done |
| Corpus frozen | done — `hlk8s`, 99 segments, 2952.821 s, source SHA-256 `4b88b8d5…f0f39fd9` |
| Reference | done — the publisher's human transcript, independent of every engine ranked |
| Engine runs | done — 5 engines and 2 prompted Whisper configurations, 99/99 segments each, on our own GPUs |
| Report | **published** — <https://stt.nddev.it.com/> |
| Recommendation | **Whisper `large-v3-turbo` with a glossary prompt** for production. `large-v3` was **retracted**: it collapses on 19 of 99 segments. Conditional and two-level — the report states the conditions |

## Envelope

Open models only, run on the employer's own GPUs. Nothing paid, no cloud STT,
not even free tiers, so the audio was sent to no vendor and the employer can
re-run the whole benchmark without buying anything. Two self-hosted engines
(Whisper large-v3, Parakeet) need no account at all, so the benchmark has a
floor that no account failure can remove. If fewer than five engines are
reachable within the envelope, the report names the specific blocker per engine
rather than quietly reporting four.

## Running it

```bash
uv run --with pytest pytest tests/test_task2_metrics.py tests/test_task2_bootstrap.py \
                            tests/test_task2_harness.py -q
```
