# Task 1 — Spend Observability

## Files

| File | Role |
|---|---|
| `raw_sampler.py` | bootstrap collector, live on `server-nddev-amsterdam` since T0 |
| `monitor.py` | full monitor: adapters, metrics, alerting, dashboard *(in progress)* |
| `alerts.jsonl` | one JSON object per line, the alerting deliverable |
| `data/` | captured samples, gitignored, authoritative copy lives on the server |

## Bootstrap collector

`raw_sampler.py` deliberately does no parsing. It records `ts`, `provider`,
`http`, `latency_ms` and the verbatim response body for all 15 providers every
30 seconds. Because it interprets nothing, later decisions about schema
adapters, burn-rate windows and alert thresholds can be replayed against data
captured before those decisions existed.

Started **2026-08-23T16:14Z**; earliest valid 6-hour mark **2026-08-23T22:14Z**.

## Provider taxonomy

Four pay models, which are never aggregated together:

| Pay model | Providers | Value means |
|---|---|---|
| `prepaid_balance` | brightdata, evomi, twocaptcha, openai, openrouter, tremendous | money left (USD, except tremendous in GBP) |
| `credits_package` | scrapfly, zerobounce, findymail, bounceban, elevenlabs, resend | quota left until `refresh` date |
| `spend_report` | anthropic, meta_ads | trailing cost, no balance at all |
| `postpaid` | vastai | credit that may legitimately go negative |

Provider IDs are opaque keys: `brightdata` reports as "Oxylabs", `meta_ads` as
"Google Ads", `openrouter` as "Groq". Nothing is inferred from the ID.
