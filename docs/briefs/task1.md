# Brief — Task 1: Spend Observability

**Status: COMPLETE — historical.** The Task 1 brief as issued to its agent. Delivered.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


You own Task 1 end to end. This session is one task, one trace: everything you do
here becomes `task1-spend-observability/TRACE.md`, exported verbatim at the end.

## Read first, in this order

1. `AGENTS.md` — non-negotiable rules. Rule 1 (never stop the collector), rule 2
   (secrets), rule 3 (do not enumerate unrelated infrastructure) are binding.
2. `README.md` — what the live API actually does, measured.
3. `docs/RUNLOG.md` — what is deployed where, with timestamps.
4. `docs/HANDOFF.md` — how to reach the collector.

## State of the world

The raw collector went live at **T0 = 2026-08-23T16:13:26Z** on
`server-nddev-amsterdam` as `explee-raw-sampler.service`, writing verbatim
responses to `/opt/explee-spend-monitor/data/raw_samples.jsonl` every 30 s.
It is `active` and has no gaps. The earliest valid 6-hour mark is
**2026-08-23T22:14Z**.

Note for this machine: the `server-nddev-amsterdam` SSH alias was pointing at a
stale IP and has been corrected. If SSH still fails, say so — do not redeploy
the collector, and do not restart it. Losing that window is unrecoverable.

## What to build

The task asks for two things: a dashboard where **one glance** tells you what is
happening with company spend, and alerting that appends a line to `alerts.jsonl`
when a human should look.

Deliverables: `task1-spend-observability/monitor.py` (the code, one file),
`alerts.jsonl`, a publicly deployed dashboard that opens with no login, and
`TRACE.md`.

## Architecture guidance — not a spec

The raw sampler is the append-only source of truth. Strongly prefer a monitor
that **derives** state from `raw_samples.jsonl` (replay the whole history on
start, then tail it) rather than adding a second poller against the API. That
gives three things for free: the dashboard shows history from T0, every alert
rule can be recomputed against the full window when you change a threshold, and
the third-party API sees one client instead of two.

Persist derived state in SQLite (WAL). History and alert dedup state must both
survive a restart.

## What the data already proves — verify it yourself, do not take it on faith

- Provider IDs are opaque keys and do not match display names (`brightdata` →
  "Oxylabs", `meta_ads` → "Google Ads"). Never infer a real vendor API from an ID.
- Four pay models with incompatible semantics: prepaid balance (USD and GBP),
  credits package with a refresh date, trailing spend report, postpaid credit
  that can legitimately go negative. **Never sum across pay models or
  currencies.** A single "total spend" number would be fiction.
- Response shapes differ per provider, including nested wallets, `amount_cents`,
  and bare `{"gbp": ...}`. Read what actually comes back in the captured log.
- HTTP 429 appears to be injected pool-wide, not per provider. An availability
  rule that fires per provider will produce spam. Verify this against the
  captured data before designing around it.
- `{}` is a third state, distinct from a value and from an HTTP error. Parsing
  it as `0` would fabricate a balance collapse.
- Balances get topped up. That is normal operations, not an incident. A positive
  jump is an event to record, never an alert.

## Alerting

Separate two classes of rule and label them honestly:

- **Operational policy** (runway lead time, unavailability tolerance): cannot be
  derived from the data because the employer never gave an SLA or a floor. Put
  these in config and state them as assumptions.
- **Data-derived baselines** (burn rate, its dispersion, anomaly thresholds):
  computed from the observed window. Use robust statistics — median and MAD, or
  Theil–Sen — not a naive first/last difference, because 429/504 tear holes in
  the series and top-ups add positive jumps.

Every alert needs a sustain period, deduplication, cooldown, and persisted
state, so a flapping provider produces one line and not two hundred. Each line
is one JSON object on one physical line. Required keys: `ts` (ISO-8601 **with an
explicit offset or `Z`**) and `text`. Include `provider` (the catalog ID),
and carry the evidence — the observed value, the rate, the projection — so a
human can act on the line alone.

A single timeout must not produce an alert. Neither must a top-up, a package
reset on its refresh date, or a postpaid credit going negative on its own.

## Dashboard

Sorted by risk, not alphabetically. Show freshness explicitly — stale data
displayed as fresh is worse than a gap. Show per-provider unit and pay model,
burn, runway or projected-at-refresh, a sparkline over the window, active
alerts, recent top-ups and resets as events, and collection health. Aggregate
only within a unit.

Deploy on `server-nddev-amsterdam` behind whatever reverse proxy is already
there. Public URL, no login, HTTPS. Add `/healthz` that reports unhealthy when
the process is up but every provider's data is stale.

## Definition of done

- 15 providers present; ≥6 h of real samples; start/end and sample count prove it.
- Restart preserves history and alert state.
- Timeouts and malformed payloads do not crash the process.
- Top-ups do not alert; every alert carries evidence and survives a skeptical read.
- `alerts.jsonl` parses line by line; every timestamp is timezone-aware.
- Public URL opens in incognito.
- `uv run --with pytest pytest tests/ -q && ruff check .` passes.

## Working discipline

Be data-driven: every claim is a hypothesis plus the measurement behind it. If
something cannot be measured, say so instead of estimating quietly.

Append what you deploy and when to `docs/RUNLOG.md`. Commit as you go with real
messages. Do not touch `task2-*` or `task3-*`.

Report progress to the orchestrator session when you hit a milestone or a
blocker. If you need a decision that is the human's to make, state it plainly
rather than guessing.
