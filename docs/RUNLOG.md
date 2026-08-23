# Run log

Append-only record of what was deployed, when, and what proved it.

## 2026-08-23

### 16:02Z — first API reconnaissance
Catalog returned 15 providers across four pay models: 6 prepaid balance,
6 credits package, 2 spend report, 1 postpaid. Provider IDs do not match display
names (`brightdata` → "Oxylabs", `meta_ads` → "Google Ads"), so the ID is treated
as an opaque key and never used to infer a vendor's real API shape.

Anomalies observed within the first minutes, all recorded verbatim:
- `tremendous` → `429 {"error":"rate limited"}` and `504` on repeat calls
- `findymail` → `429` in the same cycle as `tremendous` (429 is pool-wide)
- `anthropic` → `{}` once, then `{"object":"cost_report","amount_cents":3333,...}`

### 16:10Z–16:13Z — amsterdam droplet resize
Upgraded to run the monitor on better hardware before starting the long capture,
so no resize downtime would land inside the observation window.

| | |
|---|---|
| Droplet | `593033197` / `nddev-amsterdam` / `ams3` |
| Before | `s-8vcpu-16gb` (Basic, `DO-Regular` CPU), 96 USD/mo |
| After | `s-8vcpu-16gb-intel` (Basic Intel, `DO-Premium-Intel` CPU), 112 USD/mo |
| Disk | 320 GB unchanged, so the resize is reversible |
| Downtime | 2 min 19 s (16:10:47Z shutdown → 16:13:06Z containers healthy) |

Pre-flight check: all seven containers carry `restart: unless-stopped` and
`docker` is `enabled`, so recovery needed no manual step. Verified after:
`captcha.nddev.it.com` 200 in 0.377 s (was 0.538 s),
`unrelated-client-b` 200 in 0.494 s (was 0.593 s).

### 16:14Z — T0, raw capture live
`explee-raw-sampler.service` enabled and started on `server-nddev-amsterdam`.

| | |
|---|---|
| Unit | `/etc/systemd/system/explee-raw-sampler.service` |
| Script | `/opt/explee-spend-monitor/raw_sampler.py` |
| Data | `/opt/explee-spend-monitor/data/raw_samples.jsonl` |
| Interval | 30 s, per-request timeout 10 s, concurrency 5 |
| Restart | `always`, unit `enabled` so it survives reboot |

The sampler stores raw response bodies with no parsing. That makes the log a
superset of anything a later monitor needs, so schema decisions taken tomorrow
still apply to data captured today.

Earliest valid 6-hour mark: **2026-08-23T22:14Z**.

### 16:25Z — trace exporter hardened by using it

Three defects surfaced only by running the tool against a real session, each
fixed rather than worked around:

1. **40-hex pattern matched every git SHA.** A generic `[0-9a-f]{40}` rule
   cannot tell a Deepgram key from a commit hash. Left in, it would have made
   `--allow-secrets` routine, which is worse than having no scanner. Replaced
   with a context-bound rule that requires an assignment (`API_KEY=…`).
2. **`\b` never fired inside `DEEPGRAM_API_KEY`.** There is no word boundary
   between `M` and `_`, so the assignment rule missed the most common real
   shape. Caught by the scanner's own test table, which asserts both directions.
3. **Turn numbers are not a stable acknowledgement key.** A live session grows
   while it is being worked on, so every `--allow-finding 'turn 176: …'` went
   stale within minutes — and the export correctly refused rather than silently
   accepting a review of a different turn. Findings are now identified by
   `sha256(matched)[:12]`, which survives renumbering.

Findings acknowledged for the orchestration export, all synthetic fixtures from
the turns that wrote the test suite, each read before acknowledging:
`anthropic key:276f03f3a1d2`, `openai key:a4f3b2153f32`,
`github token:620e24b63197`, `bearer token:7ecaa9898bcf`,
`assigned api key:86cbb4aba6a3`, `private key block:03d104c669e3`,
`aws access key:1a5d44a2dca1` (the AWS canonical documentation example).

### 16:27Z — confidentiality finding on the orchestration trace

Scanning the exported orchestration trace showed it carries material that has
nothing to do with this submission:

| Leak | Count |
|---|---|
| Distinct third-party server IPs | 9 |
| `HostName` lines from `~/.ssh/config` | 16 |
| Unrelated client/project names | unrelated-client-b ×45, unrelated-client-a ×10, and 9 others |

Cause: early reconnaissance listed SSH hosts and `Developer/` to pick a deploy
target, which was reasonable locally and unacceptable in a published artifact.
Redacting it would violate the verbatim requirement, so the trace stays internal
instead. `AGENTS.md` rule 3 now forbids the reconnaissance pattern that created
it, so the three task traces will be clean by construction.

### 16:25Z — GDS registration

Repository registered against the GDS estate standard:

| | |
|---|---|
| Repository id | `repo_01M0QPEFY0YJFX2XGGCBG4FMZF` |
| Provider | `rldyourmnd/explee-ai-dev-test` (id `1343959619`, private) |
| Device | `rldyourmnd-ubuntu-1` (`device_0Q0MPJ4Z2ENZ97XWETRESKZGTH`) |
| Plan | `plan_01M0QQ2AWAHKE9ECP3VK44DVMV`, applied |
| Bundle | `0.4.0-dev`, digest `sha256:9bc36b13cbe2…` |

`gds validate repository` passes and the projections
(`.gds/bundle.lock.yaml`, `.gds/compiled-policy.json`) are materialized.
`AGENTS.md` stays author-owned: the anchor sets `agent.generated_agents: false`,
so the generator does not overwrite it.

`gds doctor` still reports `GDS_CONTEXT_POLICY_EMBEDDED_TEMPLATE_MISMATCH`. That
is estate drift, not a defect in this repository: the installed binary is
`gds 0.6.0+source.3f98c262c605` while the control-plane source has moved on to
`b2dea28`, so the generator's embedded templates trail their canonical source.
The control-plane repository itself passes `gds doctor`, which confirms the
canonical side is intact. Rebuilding the GDS release is out of scope here.

### 17:10Z — monitor deployed, reachable through the existing edge proxy

`monitor.py` runs as a container on the reverse-proxy network. It is the only
consumer of the raw log; the sampler was not touched and
`systemctl is-active explee-raw-sampler` returned `active` before and after.

| | |
|---|---|
| Container | `explee-spend-monitor`, `python:3.13-slim`, `restart: unless-stopped` |
| Network | `nddev_reverse_proxy` (existing `nginxproxy/nginx-proxy` + `acme-companion`) |
| Routing | `VIRTUAL_HOST=spend.nddev.it.com`, `VIRTUAL_PORT=8770` |
| Raw log | `/opt/explee-spend-monitor/data` mounted **read-only** |
| Derived state | `/opt/explee-spend-monitor/state` (SQLite WAL + `alerts.jsonl`) |
| Published ports | none — reachable only via the edge proxy |

The read-only mount is deliberate: rule 1 says the capture must never be
disturbed, and a `:ro` bind makes that structural rather than a promise. Replay
of 1856 records took 5.3 s on the droplet.

Verified through the edge proxy with an explicit `Host` header, because DNS does
not exist yet:

```
GET /        -> HTTP 200, 42145 bytes, 0.078 s
GET /healthz -> HTTP 200, 15 providers, 14 fresh, 1 stale (bounceban, mid-outage)
```

**Blocked on one thing that is not mine to do: DNS.** `nddev.it.com` is served by
`ns23/ns24.domaincontrol.com` (GoDaddy), not DigitalOcean, so `doctl` cannot
create the record; `doctl compute domain get nddev.it.com` returns 404 and the
account manages zero domains. No GoDaddy, Cloudflare or DigitalOcean token is
present in the environment, and rule 2 forbids obtaining one by pasting it into
a prompt. There is no wildcard record to inherit: both `spend.nddev.it.com` and a
control probe resolve to nothing.

A wildcard-DNS shortcut such as `nip.io` was rejected rather than overlooked: it
encodes the server address in the hostname, so the public URL would carry an IP
straight into a published trace and fail the rule 3 scan by construction.

Once an `A` record for `spend.nddev.it.com` points at the same address as the
other hosts already served by this proxy, `acme-companion` issues the
certificate unattended and the public HTTPS URL comes up with no further
deploy step. Nothing else is waiting on it.

### 17:38Z — phantom-spend defect found by looking at the dashboard, fixed and redeployed

Rendering the deployed page and reading it caught a defect no test had asked
about. `twocaptcha` was showing **133.07 USD/h burn and 0.5 h to impact** for a
provider that actually burns 0.28 USD/h with roughly 250 h of runway.

The raw log shows what happened, verbatim:

```
17:25:30 {"balance":72.63}      17:29:30 {"balance":82.61}
17:26:00 {"balance":82.63}  <-- +10.00      17:30:00 {"balance":72.64}  <-- given back
```

The API returned +10.00 USD for exactly eight polls and then took it back. The
monitor classified the rise as a top-up and cut the burn series there, which
left the reversion sitting inside the estimation window — so a 10 USD give-back
over 5.5 minutes was read as continuous spend.

**A rise that is handed back is not a top-up.** Reverted blips are now detected
by pairing a rise with a matching fall inside a 15-minute window, classified as
`reverted_blip`, and never used to cut the series. `twocaptcha` reads 0.297 USD/h
and 244.5 h again. A second blip surfaced immediately: `bounceban` +3.0 credits
held for 690 s, same shape.

Two things this exposed that are worth keeping:

1. **The projection guard earned its place.** The false runway never reached
   `alerts.jsonl`, because a projection needs 30 minutes of evidence and the
   post-cut segment had 330 s. A guard added on general principle turned out to
   be the only thing standing between a bad estimator and a false critical alert
   on the calmest provider in the estate.
2. **Event classification can improve with hindsight, and the store must allow
   it.** At 17:26Z the rise was indistinguishable from a top-up; only the
   reversion revealed it. Events were keyed on `(provider, kind, ts)`, so both
   readings persisted and a human saw two contradictory events for one moment.
   They are now keyed on `(provider, ts)` and the better-informed classification
   replaces the earlier one.

Redeployed and verified. Derived state was dropped and replayed rather than
migrated, which is the property the design exists for: the raw log is the source
of truth, so a fixed estimator can be applied to the whole window. The previous
alert file was archived as `alerts.pre-blip-fix.<ts>.jsonl`, not deleted.

```
collector before / after : active / active   (never restarted)
replay                   : 2704 records, 9.8 s
GET /healthz             : 200, 15 providers, 15 fresh, replay_complete true
alerts.jsonl             : 6 lines, regenerated against the whole window
```

Still pending, unchanged: the public DNS record. Nothing else waits on it.

### 17:50Z — restart-preserves-state verified on the deployment, not just in tests

"Restart preserves history and alert state" is a definition-of-done item, so it
was checked against the running deployment rather than only against fixtures.

```
BEFORE  alerts=6 samples=2730 fired=6 sha=35d3f1c927986b2e
AFTER   alerts=6 samples=2745 fired=6 sha=35d3f1c927986b2e
collector active before and after; never restarted
```

`alerts.jsonl` is byte-identical across the restart — same digest, not merely
the same line count — so no live alert re-fired and no line was duplicated. All
six `last_fired` timestamps survived in `alert_state`, which is what holds the
cooldown across a process boundary. Readings grew 2730 → 2745 because the tail
picked up new samples, not because anything was re-ingested: the restart logged
`[replay] 0 records`, resuming from the stored byte offset.

The two properties are deliberately independent. Ingestion is idempotent under a
full re-read (readings key on `(provider, ts)`, alerts on a content hash), so a
lost offset would cost time and not correctness; the offset is an optimisation
on top, not the thing keeping the file clean.

### 17:52Z — 429 correction landed in the repository README

The "429 is injected pool-wide" row was withdrawn and replaced with the measured
result, with the superseded claim struck through rather than deleted. A wrong
measurement that reached a design decision is worth leaving visible.

### 18:05Z — spend-report burn was an order of magnitude wrong; corrected

A second read of the rendered dashboard caught a semantics error in the two
`spend_report` providers. Burn was being computed as the fitted slope of the
reported value — but that value is a trailing-window total, not a balance.

With `V(t)` the spend over `[t−24h, t]`:

```
dV/dt = r(t) − r(t−24h)
```

which is zero while spending steadily and negative whenever the window rolls
off faster than new cost lands. The dashboard was therefore showing:

| Provider | shown as burn | actually |
|---|---|---|
| `anthropic` | 32.81 USD/h | 81.70 USD per 24 h = **3.40 USD/h** |
| `meta_ads` | **−11.39 USD/h** | 340.47 USD per 24 h = **14.19 USD/h** |

A negative burn on a paid-ads account reads as income. Both numbers are now
`V / window`, with the window parsed from the payload (`"window":
"trailing_24h"`) rather than assumed. The derivative is kept but labelled as
what it is — a `trend`, feeding the anomaly rule — and the burn-anomaly text for
these two providers no longer describes an acceleration as a spend rate.

This is the same class of error as reading `{}` as zero: a plausible number in
the right units that means something else. It survived the unit tests because
every test asserted the estimator was internally consistent, and none asserted
the estimate meant what the column header claimed.

### 18:00Z — alert restatement: the live log showed the cooldown was wrong

The watch fired four alerts at 17:49Z and reading them showed the failure mode
a cooldown creates. Compared against the same four rules an hour earlier:

| Provider | 16:48Z | 17:49Z | new information? |
|---|---|---|---|
| `elevenlabs` | 44.0 h | 42.7 h | no — 3% drift |
| `scrapfly` | 134.9 h | 130.0 h | no — 4% drift |
| `openrouter` | 55.6 h | 52.1 h | no — 6% drift |
| `resend` | 182.0 h | **44.9 h** | **yes — fourfold deterioration** |

Three lines a human cannot act on, printed alongside the one they must, and
formatted identically. That is how an alert channel gets ignored.

Lines are now written when a condition **starts** and when it **crosses a
materiality band** — roughly doubling steps of time-to-impact, outage duration
or anomaly deviation — never merely because time passed. Bands carry a
direction, so a condition that eases lowers its stored band silently instead of
announcing its own recovery, and a relapse still speaks.

Re-evaluated against the whole window, which is the property the append-only
design exists for:

```
before: 10 lines, 4 of them restatements
after :  9 lines, every one a start or a deterioration
        resend reads as a narrative: 182.0 -> 157.1 -> 71.8 -> 47.8 h
```

The `burn_anomaly` line for `resend` easing from 20.4 to 14.0 MAD is gone, which
is correct: nobody acts on an anomaly getting smaller.

One latent defect fixed alongside it. The stored signature was overwritten on
every evaluation, so it tracked the last thing *evaluated* rather than the last
line *written*. A condition drifting across a band while suppressed would have
had its change absorbed silently and never announced. It now records the band as
of the last written line.

### 18:20Z — replay determinism verified against the live instance

The README claims that deleting derived state and replaying re-applies a
changed threshold to the whole window, and that sustain periods evaluated on
the data clock make a replay reproduce what a live run produced. Both were
checked against real data rather than only against fixtures.

```
replay A vs replay B, same log      : byte-identical alerts.jsonl
replay vs the live tailing instance : 10 lines each, same (rule, provider, band)
                                      sequence
```

The live instance built its log incrementally by tailing over ninety minutes;
the replay rebuilt it in one pass from an empty database. They agree. Fired
timestamps are not compared, because the tail loop also evaluates on the wall
clock so staleness still fires when the sampler dies — the *decisions* match,
which is the property that matters.

### 18:18Z — two more defects, both found by exercising the deliverable

**`/healthz` was only reachable through a socket.** The health decision lived
inside the request handler, so the 503 path could not be unit-tested. It is now
`healthz(store, replay_complete, now)` with the handler reduced to plumbing.
Verified end to end against a log whose newest sample was two hours old:

```
GET /healthz -> 503 unhealthy, "every provider's data is stale", 0/15 fresh
GET /        -> 200
```

The dashboard deliberately keeps serving while unhealthy: an operator
investigating the probe needs to be able to look at it.

**The evidence panel printed malformed JSON.** It rendered
`json.dumps(evidence)[:400]`, which clips mid-token — the page carried
fragments like `"threshold_h": 72.0, "`. A panel whose entire purpose is
carrying the evidence for a claim should not display broken JSON. Fields are
now rendered complete as `key=value` pairs.

### 18:10Z — cold replay was doing three times the work it needed

Replay scaled as O(n^1.85), which at the six-hour mark is minutes on the
droplet. Most of it was redundancy: `detect_discontinuities` ran three times per
provider per tick, and event detection re-queried readings that `build_state`
had already fetched and converted. Readings and cuts are now computed once per
evaluation and shared — replay drops ~20% and the test suite with it.

Confirmed a pure refactor by replaying the same window before and after and
diffing: byte-identical `alerts.jsonl`.

### 18:26Z — concurrency check against the live deployment

The dashboard is served by a threaded HTTP server while the ingest thread
writes to the same SQLite file, so the read/write overlap was exercised rather
than assumed:

```
40 concurrent requests across / /healthz /api/state  -> 40x 200, no errors
container: running, restarts=0
collector: active
```

No non-startup lines in the container log. Per-thread connections plus WAL and a
30 s busy timeout hold up; the writer never blocks a reader.
