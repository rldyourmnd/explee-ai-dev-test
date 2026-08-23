# Explee — AI Dev Test Task

Three deliverables, one repository, one module per task. Every task ships a
verbatim agent trace alongside its artifact.

| Task | Deliverable | Status |
|---|---|---|
| [1 — Spend observability](task1-spend-observability/) | `monitor.py`, `alerts.jsonl`, public dashboard | collector running, monitor in progress |
| [2 — STT comparison](task2-stt-benchmark/) | published comparison report | not started |
| [3 — Harness artifact](task3-harness-artifact/) | one harness file + 2–3 lines | not started |

## Why the collector started before anything else

Task 1 requires at least six hours of observation and the API has no history
endpoint, so the observation window cannot be reconstructed after the fact.
A deliberately minimal raw sampler went live before any dashboard code existed,
writing verbatim provider responses to disk. Everything downstream — schema
adapters, burn-rate estimation, alerting — replays that log, so no design
decision made later costs us data.

**T0 = 2026-08-23T16:14Z.** See [docs/RUNLOG.md](docs/RUNLOG.md) for what runs where.

## What the live API actually does

Measured, not assumed — from the first minutes of capture:

| Behaviour | Evidence |
|---|---|
| Spend is continuous and observable | `brightdata` 951.99 → 949.05 → 948.83 over ~2 min (≈ −6.6 USD/h) |
| HTTP 429 is injected across providers, not per-provider | `tremendous` and `findymail` both returned 429 in the same poll cycle |
| Gateway timeouts happen | `tremendous` → `504` after 3.4 s |
| A provider can return valid JSON with no fields | `anthropic` returned `{}` once, then `cost_report` on the next 8 calls |

Three design consequences:

1. **429 must not be attributed to a provider.** Because it is injected across
   the pool, an availability rule that fires per provider produces alert spam.
   The rule has to look at the error rate across all providers at once.
2. **`{}` is a third state.** Parsing it into `value = 0` would fabricate a
   balance collapse and a critical alert. It is recorded as `schema_miss`,
   distinct from both a value and an HTTP error.
3. **Burn rate must be gap-aware.** Rates are differences between polls, and
   429/504 tear holes in the series. A naive `Δbalance / Δt` across a five-minute
   hole mixes spend with any top-up that happened inside it.

## Known measurement limit

A top-up that lands in the same interval as spend is **not observable**: the API
exposes only a current value, so we see the sum of the two, never the parts.
Burn rate is therefore a lower bound during top-up intervals. This is stated
rather than smoothed over.

## Layout

```
task1-spend-observability/   collector, alerting, dashboard, alerts.jsonl, TRACE.md
task2-stt-benchmark/         eval harness, reference policy, results, TRACE.md
task3-harness-artifact/      the artifact itself, TRACE.md
tools/export_trace.py        session log -> verbatim TRACE.md
tests/                       pytest suite
docs/RUNLOG.md               what is deployed where, with timestamps
docs/HANDOFF.md              picking this up on another machine
.gds/repository.yaml         GDS repository anchor
```

## Verification

```bash
uv run --with pytest pytest tests/ -q
ruff check .
```
