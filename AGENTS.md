# Working rules for agents in this repository

## Non-negotiable

1. **Never stop the collector.** `explee-raw-sampler.service` on
   `server-nddev-amsterdam` has been capturing since T0 = 2026-08-23T16:14Z.
   The task requires ≥6 hours and the API has no history endpoint, so any
   interruption is unrecoverable. Check with
   `ssh server-nddev-amsterdam systemctl is-active explee-raw-sampler` before
   and after touching that host.

2. **Secrets only through environment variables, never echoed.** Traces are
   published verbatim, so a key printed once is a key published. Do not run
   `env`, do not `cat .env`, do not paste keys into prompts, do not log
   `Authorization` headers. `tools/export_trace.py` refuses to export when it
   finds a credential rather than redacting one, because redaction would break
   the verbatim guarantee.

3. **Traces are exported, never written.** A TRACE.md is produced only by
   `tools/export_trace.py` from a real session log. Do not compose, summarise,
   tidy, or reorder a trace. Failed attempts and corrections stay in.

## Evidence

Every claim in a deliverable is a hypothesis plus the data behind it. "The API
is flaky" is not a finding; "429 on `tremendous` and `findymail` in the same
poll cycle at 16:01Z, 2 of 15 providers" is. If something cannot be measured,
say so explicitly instead of estimating quietly — the top-up/spend ambiguity in
`README.md` is the worked example.

## Time

All timestamps are timezone-aware. This machine is UTC+5 (Asia/Almaty) and the
work is graded across timezones, so every emitted timestamp carries an explicit
offset or a `Z`. Never emit a naive local time.

## Units

Never sum across pay models or currencies. USD balance, GBP balance, package
credits, trailing spend and postpaid credit are five different things; a single
"total spend" number mixing them would be fiction. Aggregate only within a unit.

## Verification before delivery

```bash
uv run --with pytest pytest tests/ -q && ruff check .
```
