# Explee — AI Dev Test Task

Three deliverables, one repository, one module per task. **Every task ships a
verbatim agent trace**, exported by `tools/export_trace.py` from a real session —
never hand-written, never truncated.

An earlier Task 3 trace was quarantined for a confidentiality leak and replaced
by a genuine fresh session rather than reconstructed or edited; the incident is
kept at [`docs/task3-trace-quarantine.md`](docs/task3-trace-quarantine.md)
because a recorded leak is data and a concealed one is not.

| Task | Deliverable | Status |
|---|---|---|
| [1 — Spend observability](task1-spend-observability/) | `monitor.py`, `alerts.jsonl`, public dashboard | collector gap-free since T0, max gap 29.670 s; dashboard live at [spend.nddev.it.com](https://spend.nddev.it.com/) — HTTP 200, valid certificate, no login, verified externally |
| [2 — STT comparison](task2-stt-benchmark/) | published comparison report | **published** at [stt.nddev.it.com](https://stt.nddev.it.com/) — 5 engines plus 2 tuned tracks over 99 hashed segments (2952.821 s) against a publisher human transcript; design frozen before any output was read; recommends Whisper large-v3 with a glossary prompt |
| [3 — Harness artifact](task3-harness-artifact/) | one harness file + 2–3 lines | artifact, its 2–3 lines and its trace all delivered |

Live status, with the measurement behind every claim, is in
[docs/ORCHESTRATION.md](docs/ORCHESTRATION.md).

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
| ~~HTTP 429 is injected across providers, not per-provider~~ **withdrawn, see below** | ~~`tremendous` and `findymail` both returned 429 in the same poll cycle~~ |
| HTTP 429 is per-provider | over 66 captured cycles, 429 hit **exactly one** provider each time, never two |
| Gateway timeouts happen | `tremendous` → `504` after 3.4 s, ~3.1 s latency against 110 ms normal |
| A provider can return valid JSON with no fields | `anthropic` returned `{}` once, then `cost_report` on the next 8 calls |

**Correction.** The pool-wide reading of 429 was drawn from reconnaissance at
16:01Z — twelve minutes *before* T0 — so it is not in the captured window at
all, and it does not survive it. Task 1 re-tested it against 66 exact poll
cycles and found 429 confined to `tremendous` (16×) and `findymail` (12×), one
provider at a time, in runs of 1–2 cycles. The sustained per-provider signal is
5xx: `meta_ads` 16 consecutive cycles, `bounceban` 13, `findymail` 11,
`zerobounce` 11. This entry is left visible rather than quietly rewritten,
because a wrong measurement that got shipped into a design is itself worth
recording.

Three design consequences:

1. **Availability is per provider, with a sustain period.** 429 is not pool-wide,
   so grouping availability across the pool would have hidden four genuine
   multi-minute outages. What prevents spam from 504 singles is the length of
   the staleness window (900 s, above the longest outage measured), not a
   pool-wide grouping. A separate pool-wide rule still exists for the case where
   most of the estate goes dark at once, thresholded above the worst cycle
   observed (4 of 15).
2. **`{}` is a third state.** Parsing it into `value = 0` would fabricate a
   balance collapse and a critical alert. It is recorded as `schema_miss`,
   distinct from both a value and an HTTP error.
3. **Burn rate must be gap-aware and jump-aware.** Rates are differences between
   polls, and 429/504 tear holes in the series. A naive `Δbalance / Δt` across a
   five-minute hole mixes spend with any top-up that happened inside it — for
   `findymail` it reports the balance *rising* by 3623 credits/h.

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
