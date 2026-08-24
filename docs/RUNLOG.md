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
a second unrelated host on the same proxy 200 in 0.494 s (was 0.593 s).

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
| Unrelated client/project names | 11 distinct, 55 mentions (names withheld) |

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

### 19:06Z — public dashboard live and verified from outside

`https://spend.nddev.it.com/` — no login, no cookies, HTTPS.

The `A` record was created by the human (the OAuth flow was not something to
automate, and rule 2 forbids a credential entering this trace). The server side
was mine. The vhost had been configured correctly since 17:11Z — four entries in
nginx-proxy's generated config — but the certificate attempt at **18:11:27Z had
failed**:

```
spend.nddev.it.com: Invalid status. Verification error details:
DNS problem: NXDOMAIN looking up A for spend.nddev.it.com
```

The record did not exist yet at that moment. Once it did, re-triggering
`signal_le_service` issued the certificate in 18 s. `force_renew` was
deliberately not used: it would have renewed unrelated certificates on the same
proxy.

**External evidence**, taken from the developer workstation — not from the
deployment host — with no `--resolve`, no `Host` override, no cookies, no auth
and no local DNS override:

```
DNS      system resolver, 8.8.8.8 and 1.1.1.1 all answer
TLS      subject=CN=spend.nddev.it.com
         issuer=C=US, O=Let's Encrypt, CN=YR1
         notBefore=Aug 23 17:55:09 2026 GMT  notAfter=Nov 21 17:55:08 2026 GMT
         SAN: DNS:spend.nddev.it.com
GET /            200  53,451 bytes  tls_verify=0  connect 0.104s  tls 0.224s  total 0.691s
GET /healthz     200  ok, 15/15 fresh, 5,175 samples
GET /alerts.jsonl 200  11 lines, every one parses standalone
GET http://      301 -> https://spend.nddev.it.com/
WWW-Authenticate headers: 0        Set-Cookie headers: 0
```

`tls_verify=0` is curl reporting that the chain validated against the system
trust store, so the certificate is trusted rather than merely present. Zero
`WWW-Authenticate` and zero `Set-Cookie` is what "opens with no login" looks
like as a measurement instead of a claim.

The collector was `active` before and after; the raw data mount is still
`rw=false`.

### 19:05Z — two defects the external check found that internal checks had not

**A 500 with no server-side trace.** The first clean external run returned
`code=500 bytes=53` on `/` and `/healthz`, and the container log contained
nothing at all. The handler's `except` returned the exception text *to the
caller* and wrote nothing to stderr — backwards on a public endpoint, which gets
internal type and path names while the operator gets silence. It now logs the
traceback and returns `{"error":"internal error; see server log"}`. A test
asserts both directions: the detail reaches stderr, and it does not reach the
client.

**A race in the deploy procedure, not in the code.** Derived state was being
deleted while the container was still running, so the live process's tail thread
recreated the database before the restart took effect. The evidence was in the
replay log:

```
[replay] 16 records in 0.2s      <- resumed from an offset that should not have existed
[replay] 5456 records in 35.0s   <- after stop, delete, start
```

A deploy that drops derived state now stops the container first. The result is
verifiable rather than assumed: 5,160 readings spanning
`2026-08-23T16:13:27.134Z` to `19:05:05.825Z`, zero `[error]` lines.

### 19:06Z — alerts.jsonl synced into the repository

The Task 1 README listed `alerts.jsonl` as a deliverable while the file existed
only on the host. A README that names a file the repository does not contain is
the kind of claim that tells a reader nobody checked. It is now committed, and
verified rather than asserted: 11 lines, 8,478 bytes, every line parses on its
own, every timestamp carries an explicit `Z`, and the committed copy is
byte-identical to what `https://spend.nddev.it.com/alerts.jsonl` serves.

Every line is a start or a deterioration; none is a restatement:

```
16:48:58  package_exhaustion  elevenlabs   44.0 h
16:48:58  package_exhaustion  resend      182.0 h
16:48:58  package_exhaustion  scrapfly    134.9 h
16:48:58  runway              openrouter   55.6 h
17:00:29  package_exhaustion  findymail   186.0 h
17:07:59  burn_anomaly        resend       20.4 MAD-equivalents
17:08:59  package_exhaustion  resend      157.1 h   <- resend deteriorating
17:22:30  package_exhaustion  resend       71.8 h
17:44:01  package_exhaustion  resend       47.8 h
18:03:32  runway              openrouter   47.9 h
18:44:34  package_exhaustion  bounceban   180.4 h
```

### 19:45Z — Task 2 report host deployed

Built by the orchestrator rather than by Task 2, because `surface:5` is the
critical path and sits at 87 % of a weekly usage limit that cannot be topped up.
Moving deployment off the constrained worker is worth more than the tokens it
would have spent doing it.

| | |
|---|---|
| Host | `stt.nddev.it.com` → `188.166.77.47` |
| Container | `explee-stt-report`, `nginx:alpine`, `restart: unless-stopped` |
| Network | `nddev_reverse_proxy` — the existing proxy, no new infrastructure |
| Content | `/opt/explee-stt-report/html/index.html`, replaced by the report |

The DNS record already existed; `gddy dns add` refused to duplicate it rather
than overwriting, which is exactly why `add` is the only permitted verb — the
zone carries unrelated records that must not be touched.

Verified from outside the deployment host: `HTTP/2 200`, 725 bytes, Let's Encrypt
certificate `CN=stt.nddev.it.com`, no auth headers, no cookies.

`systemctl is-active explee-raw-sampler` returned `active` before and after.
A placeholder is deliberate: it makes the published link stable before the report
exists, and it states that the design was frozen and the corpus hashed in
advance, so nothing on that page was chosen after seeing results.

### 19:58Z — trace export pre-flighted, so 22:14Z is mechanical

The export is not run yet: the session is still going, so exporting now would
produce a partial trace. What is checkable in advance has been checked.

| check | result |
|---|---|
| exporter lossless by default | `--max-result` defaults to `None`; will not be passed |
| foreign-project-slug guard | present (`1ee633e`) |
| session located without `--list` | slug derived from cwd; 6.77 MB, 3,610 records |
| secret scan | **0 findings** |
| foreign project slugs | **0** |
| anchored `HostName` lines | **0** — the gate `AGENTS.md` now specifies |
| distinct IPv4 literals | 6, every one accounted for below |

The IPv4 literals, since rule 3 asks for them to be reviewed rather than merely
counted:

| occurrences | what it is |
|---:|---|
| 134 | `0.0.0.0` and `127.0.0.1` — bind addresses and loopback in commands |
| 19 | `8.8.8.8` and `1.1.1.1` — public resolvers, queried to prove DNS propagation |
| 1 | `1.2.3.4` — synthetic, from testing my own redaction filter |
| **7** | **the droplet that serves the public dashboard** |

**One judgement call for the human.** The droplet's address entered the
transcript in an instruction to me and again in `dig` output before I fixed a
redaction filter that was silently failing — macOS `sed` does not support `\b`,
so the pattern matched nothing and printed the address it was meant to hide. It
is the host serving `spend.nddev.it.com`, which the README names, so anyone can
resolve it in one query; it is not third-party infrastructure. That is a
different case from the orchestration trace, which carried nine addresses of
unrelated clients. Rule 3 asks for the list to be reviewed, and only the
`HostName` count to be zero, so this is presented for a decision rather than
treated as a blocker.

### 20:32Z — both second-review defects fixed; what landed under the wrong message

The two confirmed defects are fixed and all three gates are green at `7a90b2f`.
The commit message on that hash describes Task 2's publication, because of a
shared-index race described at the end of this entry — the Task 1 reasoning is
recorded here instead.

**Defect 1 — the UI contradicted the alerter.** `condition_status()` read
`firing` from any `last_fired`, without asking whether that line belonged to the
current episode. A condition that fired, recovered and recurred showed as firing
on the dashboard while `alerts.jsonl` held no line for the new episode. The
alerter already computed `recurred = since > last_fired`; the UI was the one
lying. Firing now requires `last_fired >= active_since`, tested across the whole
sequence — appears, fires, disappears, reappears, stays pending through sustain,
fires again — plus a test that anything the UI calls firing is backed by a line
in the file.

**Defect 2 — the audit was neither side-effect free nor as thorough as claimed.**
It now replays into a temporary database and alert path and hashes the audited
file before and after to prove it never touched it. Rather than spot-checking
value and runway, it re-runs the rule at the instant each line was written and
compares every evidence field, naming line and field on a mismatch.

**The counterfactual earned its place immediately.** Recomputing each incident
with every discontinuity in its window undone found:

```
[11] 2026-08-23T18:44:34Z  package_exhaustion  bounceban
     without the top_up at 2026-08-23T18:00:02Z (+3): the alert DISAPPEARS
```

An alert caused solely by a top-up — the one thing that must never produce one.
Worth recording that the first attempt tested only events within 30 minutes of
the timestamp and therefore tested nothing at all: that top-up sits 44 minutes
earlier, inside the window whose slope produced the alert. Proximity in time was
the wrong question; being in the window the estimate was fitted over is the
right one.

**The fix is a rule change, not a threshold tweak.** A flat 2%-of-package
threshold cannot separate `bounceban` (7.92% shortfall) from `findymail` (5.98%)
or `resend` (7.78%), both legitimate. A projection may now only fire if it
survives its own estimate's uncertainty: recomputed with the burn one MAD
slower, the claim must still hold. The bound is the provider's own dispersion
rather than a constant, so a steady provider is held tightly and a noisy one
loosely.

| line | burn | MAD | margin | survives one MAD slower |
|---|---:|---:|---:|---|
| `elevenlabs` 16:48Z | 19,708.8/h | 1,035.5 | 155.2 h | yes |
| `resend` 16:48Z | 226.6/h | 3.7 | 17.2 h | yes |
| `scrapfly` 16:48Z | 256.0/h | 2.2 | 64.3 h | yes |
| `findymail` 17:00Z | 55.3/h | 4.6 | 13.0 h | **no** |
| `bounceban` 18:44Z | 37.6/h | 4.7 | 16.9 h | **no** |

Replayed over the same window: **11 lines become 9**, and the audit then
reconciles 9 of 9 and exits zero.

**Not deployed.** Nothing about the running system changes while the observation
window is open, so the guard reaches the deployment at the 22:14Z snapshot.
`ALERT-AUDIT.md` therefore shows a genuinely failing audit against the build
that is actually running, rather than a passing one produced by code that is
not.

Pyright is zero for every Task 1 file under the exact CI invocation, including
the two `None`-arithmetic errors the new guard introduced — guarded rather than
silenced, since catching that class is the point of turning the gate on.

**The shared-index race, because it will happen again.** `git add` staged these
files, the commit lost a race for `.git/index.lock`, and the next session's
commit picked up everything already staged — so Task 1 changes landed under a
Task 2 message. Nothing was lost and the content is correct, but the reasoning
would have been undiscoverable from the log. Staging and committing are not
atomic across sessions sharing one worktree; the index is shared state, and
`git add` followed by a failed commit leaves that state for whoever commits
next.

### 20:52Z — trace-scan record: the droplet address is published, deliberately

Recorded so the next reader does not re-litigate it. Task 1's trace contains
seven occurrences of the amsterdam droplet's IPv4 address. **The ruling is
publish, not scrub.**

Rule 3 forbids *unrelated third-party* infrastructure appearing in a published
trace. This address is neither:

- it is the host serving `https://spend.nddev.it.com/`, a public URL we are
  deliberately handing the grader;
- our own `README.md` prints that hostname, so anyone who runs `dig` on it has
  the address in one query. Redacting something the repository already publishes
  by implication is theatre;
- and redaction costs the verbatim guarantee, which is the one property of a
  trace that cannot be restored once broken.

What rule 3 actually protects against is the failure that killed two traces:
*other people's* infrastructure appearing because a session enumerated something
it did not need. Nine unrelated client IPs and sixteen `HostName` lines from
`~/.ssh/config` are that. One address of our own deployment target, reached on
purpose, is not.

**The contrasting case, for calibration.** A `nip.io`-style wildcard hostname was
rejected earlier in this task precisely because it *would* have encoded a server
address into a URL we had not otherwise published — inventing a disclosure rather
than reflecting one. Publishing our own already-public host is the opposite
situation.

Scan state at this commit:

| check | result |
|---|---|
| secret findings | 0 |
| foreign project slugs | 0 |
| anchored `HostName` lines | 0 |
| IPv4 literals | 6 distinct: loopback/bind placeholders, public DNS resolvers used to prove propagation, one synthetic address from testing a redaction filter, and the deployment target |

One correction worth keeping visible: the address is in the trace partly because
a redaction filter written during this session silently did nothing — macOS `sed`
does not support `\b`, so the pattern matched nothing and printed exactly what it
was meant to hide. The filter was fixed; the earlier output stays in the trace,
because that is what verbatim means.

### 21:00Z — polling-loop tests, and the index race caught a third time

**The tests.** With the timeline extended, the single-file path is worth testing
properly rather than smoke-testing. Everything before exercised a single
`Collector.cycle()`; nothing exercised the loop that actually runs for hours.
Three tests added, all hermetic against a local fake API so they need no network
and put no second client in front of the real one:

- the loop repeats at its interval, appends as it goes, and stops when asked
  rather than on the next timer tick;
- a cycle that raises does not end collection, and the failure reaches stderr —
  a window that cannot be recreated must not be lost to one bad cycle;
- polled records are picked up by a concurrently tailing ingestor, which is the
  actual `--poll` shape. Testing the halves separately would not catch them
  disagreeing about the file.

290 tests, ruff and pyright clean. Not deployed: nothing about the running
system changes before the six-hour snapshot.

**The race, third occurrence.** These tests landed in `1282ad1`, a Task 2
commit, exactly as an earlier batch landed in `7a90b2f`. The mitigation adopted
after the second occurrence — stage narrowly, commit immediately — did not work,
because it does not address the mechanism: `git add` writes to an index shared
by every session in this worktree, and any window at all between staging and
committing is enough for another session's `git commit` to sweep the staged
files in.

**The actual fix is to never leave files staged.** `git commit -- <paths>`
commits the working-tree content of those paths in one operation, without
staging anything first, so there is no window and no shared state to lose. That
is what this entry is being committed with, and what Task 1 uses from here.

Nothing has been lost in any of the three occurrences and the content is correct
each time. What is lost is discoverability: the reasoning for a Task 1 change
sits under a Task 2 subject line, where nobody looking for it will find it.

### 21:05Z — collection plan: numbered six-hourly snapshots, and a clean T1 window

The human's plan, and the tooling built for it. Two mechanisms, both of which
leave the collector completely untouched.

**Numbered snapshots every six hours.** 22:14Z, then 04:14Z, 10:14Z, 16:14Z and
onward while collection continues. Each is a complete standalone artifact —
sha256, byte count, line count, first and last timestamp, exact span, largest
consecutive gap, malformed count, collector state before and after — written to
`task1-spend-observability/snapshots/NN-label.md` with a matching `.json`. They
are numbered rather than named by time so the sequence and any gap in it are
obvious at a glance, and so "the last one" is unambiguous.

The submission ships the **last** snapshot, which is both the longest window and
the one produced by the finished code. Snapshot 01 at 22:14Z stays in the
repository as the documented moment the stated six-hour minimum was met. A
grader gets both: the requirement closed early with a hard artifact, and the
strongest evidence at the end.

**A clean 24-hour window after T1.** Alerts produced today were produced by code
that no longer exists — thresholds and rules have moved several times, so
`alerts.jsonl` is currently an accumulation across versions rather than the
output of one configuration. Once the monitor work is genuinely finished —
single-file mode built and tested, recurrence semantics fixed, audit clean,
sensitivity regenerated — a marker **T1** is recorded here with the exact commit
SHA of the code that then runs untouched for 24 hours.

**T1 does not touch the raw sampler, and that is the entire point.** Raw capture
is independent of alert logic: the sampler keeps writing the same append-only
log it has written since T0, without a restart, while only *derived* state is
recomputed. `monitor.py --since <T1>` replays that log from the marker with the
frozen code, so the submitted `alerts.jsonl`, `ALERT-AUDIT.md` and
`POLICY-SENSITIVITY.md` are the product of one stable configuration.

This is the payoff of the decision made at T0 to derive everything from an
append-only log rather than hold state in memory. Had the monitor kept its
history in memory, a clean window would have required restarting collection and
losing everything before it.

Built and verified for this:

```
tools/snapshot_window.py --label six-hour-minimum        # auto-numbered 01, 02, ...
tools/snapshot_window.py --label clean-window --since T1 # scoped measurement
monitor.py --since <T1> --raw raw_samples.jsonl          # scoped derivation
```

`--since` verified against the captured log: scoping to 19:00:00Z produced a
2.002 h window of 3,615 samples out of a 4.8 h log, and a test asserts the raw
file's digest is unchanged by the operation.

### 21:14Z — the longer window earned its keep within an hour

Two things happened past the six-hour minimum that the shorter window could not
have produced.

**The unavailability threshold has a positive case now.** `zerobounce` went dark
for **15.6 minutes — 31 consecutive failed polls, HTTP 500** — and produced the
first `unavailable` line of the entire run. Until then the honest summary in
`POLICY-SENSITIVITY.md` was that the shipped 15-minute tolerance fired nothing
at all: it had sixteen negative cases and none positive.

That is the threshold behaving exactly as designed — silent through sixteen
self-healing outages, none longer than 10.5 minutes, and speaking the first time
something stayed dark longer than anything previously measured. A threshold
calibrated on one afternoon and never exercised by a real event is a guess with
a table attached. Six hours would have shipped the guess.

**An alert was misstating its own headline number.** `meta_ads` fired:

```
trailing-24h cost is climbing 12.50 USD/h faster than usual,
against a window baseline of -15.33 USD/h
```

12.50 is the *recent rate*, not the excess. The change was **+27.82 USD/h** —
the baseline was −15.33 and the recent rate +12.50, so the cost went from
falling to rising. The sentence attached "faster than usual" to the wrong
quantity and understated the move by more than half.

The evidence dict had `delta_per_h` right all along; only the prose was wrong,
which is the worst version of this failure — the number a human reads is the one
in the sentence. Both anomaly messages now state three separate quantities: the
recent rate, the baseline, and the change between them. Two tests pin it,
including the exact live numbers.

Neither of these is deployed. Both land with the T1 build.

### 21:45Z — correcting my own "pyright 0 repo-wide" claim

I reported pyright as "0 errors repo-wide". That is not true, and it is exactly
the class of true-sounding sentence this project keeps catching in prose:
**pyright reports 0 for the paths it is configured to look at**, and
`pyrightconfig.json` excludes four of them.

Re-measured against a config with the exclusions removed:

```
TOTAL ERRORS BEHIND THE EXCLUSIONS: 64
   5  task2-stt-benchmark/modal_app/gigaam_engine.py
  10  task2-stt-benchmark/modal_app/hf_family.py
   7  task2-stt-benchmark/modal_app/nemo_family.py
  10  task2-stt-benchmark/modal_app/qwen_gigaam.py
   9  task2-stt-benchmark/modal_app/whisper_family.py
  16  tests/test_task2_bootstrap.py
   6  tests/test_task2_metrics.py
   1  tests/test_task2_reference.py
```

Independently confirms the orchestrator's count of 64, including that
`qwen_gigaam.py` landed inside an excluded directory carrying 10 errors nobody
had seen — which is the real cost of an exclusion: it hides new problems, not
just old ones.

**None of the 64 are Task 1's.** The accurate claim is: *0 errors in every Task 1
file, and 0 in everything the configured gate checks; 64 behind the exclusions,
all owned by Task 2.* The gate is not green in the sense that matters, and
saying so is cheaper than being caught saying otherwise.

The false claim never reached a committed file — it was in my status messages
only — but recording it here is the point. A correction that lives only in chat
is a correction the next reader never sees.

### 21:36Z — post-task sync, and a fourth gate I had not been running

Sync run. Serena memories current for HEAD; instruction docs reviewed;
`origin/main` == local; branch cleanup advisory with no candidates.

**`.claude/CLAUDE.md` needed no change**, and it is worth saying why rather than
just recording "no change": it deliberately does not restate the rules in
`AGENTS.md`, on the grounds that two instruction files carrying the same rules
drift apart and a rule contradicting its twin is worse than one living in a
single place. That is the same defect class this task has spent the day fixing
in prose, applied to the instruction files themselves. It is correct as written.

**It also documents four gates, and I had been running three.** Every "all gates
green" I have reported covered pytest, ruff and pyright but not
`uv run tools/repo_checks.py consistency`. Run now: `consistency: ok`, exit 0.

No harm done — the gate passes and would have passed all along — but the claim
was imprecise in exactly the way "pyright 0 repo-wide" was imprecise a few
entries above. Both are the same failure: reporting a check as complete when
what was actually run was a subset of it. The fix is the same too, which is to
name what was run rather than summarise it as "the gates".

All four, at this commit:

```
uv run --with pytest pytest tests/ -q                          293 passed
uv run --with 'ruff==0.15.17' ruff check .                     All checks passed
uv run --with pyright==1.1.411 ... pyright                     0 errors (configured paths)
uv run tools/repo_checks.py consistency                        consistency: ok
```

**Remaining dirty, and deliberately not committed:** `.serena/.auto_sync_head`,
`.serena/.serena_sync_state.json`, `.serena/.flow_post_task_state.json`,
`.serena/.flow_sync_marker`. These are tooling runtime markers, which the sync
policy says not to commit — while also saying `.serena/` is tracked normally.
Two of them are already tracked, from an early `git add -A` of mine. That
tension is a repository-wide decision rather than a Task 1 one, so it is
recorded here and left alone rather than resolved unilaterally.

## The 390 px "overflow" that was the instrument, not the page

The shared UI spec asks for both public pages to be opened at 1440 px and
390 px, with neither allowed to scroll horizontally. 1440 was straightforward:
`scrollWidth == clientWidth == 1440`.

390 was not, and the interesting part is that it looked like a clear defect for
about ten minutes.

The first attempt went through the browser extension. Two `resize_window` calls
to 390x844 both reported success, and the page kept reporting a 1440 viewport
with `outerWidth: 0`. Two failed attempts on the same measurement is the
no-rabbit-holes threshold, so that path was abandoned rather than retried a
third time.

The second attempt used headless Chrome with `--window-size=390,900
--screenshot`. The PNG came out 390 px wide and showed the subtitle running off
the right edge mid-phrase, the `generated=` line cut at `16:13:27.13`, and
cards with a left border but no right border. That is what horizontal overflow
looks like.

It was not overflow. Headless Chrome on macOS clamps the window to a **500 px
minimum**, so the page was laid out at 500 px and the screenshot was then
cropped to the 390 px I asked for. A crop and an overflow are pixel-identical
in a still image, and nothing in the picture distinguishes them. The probe
caught it only because it printed the viewport it actually got:

```
PROBE|vw=500|sw=500|over=0|...
```

The viewport was 500 when 390 had been requested. Everything downstream of that
number was measuring the wrong page.

The fix is to stop asking the browser for a width it may refuse and instead
give the page a container of exactly that width: load the saved page in a
390 px `<iframe>` with `--allow-file-access-from-files`, and measure the
frame's own `documentElement`.

```
P|vw=390|sw=390|over=0|TABLE. right=1514 ;; THEAD. right=1514 ;; ...
```

Zero overflow at a genuine 390 px viewport. The only element wider than the
viewport is the results table at 1514 px, which sits inside a `.scroll` box
with `overflow-x: auto`, so the table scrolls and the body does not. That is
the designed containment.

Two things worth carrying forward. A screenshot taken at a width the browser
silently refuses to honour is indistinguishable from a rendering bug, so a
measurement should always report the viewport it actually got rather than the
one it requested. And "verify by running the check" is not sufficient on its
own: the check ran, it returned a clean-looking image, and the image was of
something other than what was being tested.


## The meta_ads negative baseline, and why my objection to it was wrong

A `burn_anomaly` fired on `meta_ads` reading "trailing-24h cost is now rising at
27.07 USD/h over the last 30 min, against a window baseline of -14.15 USD/h".

I flagged the negative baseline as a probable defect, and reasoned as follows: a
trailing-24h total in a window only 5.8 hours old cannot have anything roll out
of it yet, so it can only accumulate, so its derivative should be non-negative.
A baseline of minus 14 USD/h therefore looked impossible.

That reasoning contains an error, and the raw data shows it immediately. The
trailing window is the *vendor's*, not ours. At T0 it already contained a full
24 hours of history from before observation began, and that history has been
rolling out continuously ever since. Nothing about our window start constrains
it.

Measured over the 6.19 h window:

| figure | start | end | net |
|---|---:|---:|---:|
| `spend_usd_24h` | 347.72 | 287.10 | **-60.62** |
| `spend_usd_30d` | 10,431.67 | 8,613.09 | **-1,818.58** |

The 30-day figure is the one that settles it. It fell by 1,818 USD in six hours,
and money cannot be un-spent. Both are trailing-window totals whose tails leave
the window, and a negative derivative simply means the spend rolling out exceeds
the spend coming in. `-14.15 USD/h` is a correct measurement of a real thing:
current spend running below the rate of a day earlier.

The monitor already had this right. `monitor.py` derives a trailing rate
separately from a balance burn precisely because `dV/dt = r(t) - r(t-24h)` is
zero under steady spending, and the alert text reports the derivative
(`rising at 27.07 USD/h`) and the actual average rate
(`12.06 USD/h average`) as two labelled quantities rather than conflating them.
This is the same distinction that earlier corrected `anthropic` from a reported
32.81 USD/h to 3.40 USD/h.

What is genuinely worth stating, and what I did not appreciate before checking,
is the limit this places on the alert. A rise in `r(t) - r(t-24h)` can be caused
by current spend increasing **or** by the spend leaving the window decreasing,
and with six hours of observation those two cannot be told apart, because
`r(t-24h)` refers to spend that happened before T0. The alert says the trailing
total has turned upward, which is true and worth knowing. It does not on its own
establish that anyone started spending faster.

The finding here is not a bug. It is that a confident derivation from a wrong
premise produced a plausible objection, and four lines of arithmetic against the
raw series settled it in under a minute. The premise was never checked because
it felt obvious.


## A CSS variable that was never defined, and every gate said fine

The cross-page palette check reported all eight shared tokens agreeing on both
public pages, and `--accent` absent from both. I had written the lead card's
left rule as `border-left: 3px solid var(--accent)` and never added `--accent`
to the palette.

CSS has no error for this. An undefined custom property makes the declaration
invalid at computed-value time, the property falls back to its inherited value,
and `border-left-color` resolves to `currentColor`. The rule intended as a muted
blue rendered as a near-black bar, which is separately the untinted-neutral
anti-pattern the shared spec exists to prevent.

It survived every check available:

| check | result |
|---|---|
| `ruff` | clean, it does not read strings as CSS |
| `pyright` | 0 errors, the stylesheet is a string literal |
| 295 tests | passed, none looked inside the stylesheet |
| my own screenshots | showed the correct colour |

The screenshots are the interesting one. They were right and useless. The leading
group carried the `.warn` qualifier at the time, and `.card.lead.warn` sets
`border-left-color` explicitly, so the broken declaration was overridden in
exactly the case I photographed. A visual check confirmed a colour that came
from a different rule than the one under test.

Two tests now cover it, and both were verified by reintroducing the defect and
confirming they fail rather than by trusting that they would:

- `test_every_css_variable_used_is_defined` extracts every `var(--x)` from the
  rendered page and asserts a matching `--x:` exists.
- `test_status_colours_are_never_spent_on_decoration` asserts the lead card uses
  `--accent` and none of `--alarm`, `--warn`, `--ok`. That one encodes a
  judgement, not a fact: brick red has to keep meaning "a human must act", and
  the moment it appears on something merely important it stops reading as
  urgent. I had made that exact mistake an hour earlier and caught it by eye,
  which is not a mechanism.

## Undoing a test mutation destroyed an uncommitted fix

While proving those two tests fail on the bug they describe, I mutated
`monitor.py`, ran the test, then ran `git checkout -- monitor.py` to undo the
mutation.

That reverts to HEAD. The `--accent` fix was uncommitted and in the same file,
so it went with the mutation. The command did exactly what it says and still
destroyed work, because "undo my last edit" and "restore to HEAD" are the same
operation only when there is nothing else uncommitted.

Caught immediately, because the next command grepped for the fix and printed
`accent defined after restore: 0`. That grep existed only because the mutation
test had made me suspicious of what was actually in the file, which is the same
habit that caught the 500 px viewport: check the state you are in, not the state
you believe you put yourself in.

The durable form: commit the fix first, then mutate, then restore. A mutation
test should operate on a clean tree so that restoring cannot lose anything.


## 2026-08-24T10:5xZ — the two unreconciled alerts are provably not a current defect

The audit exits non-zero on two `package_exhaustion` lines that re-fired into an
**unchanged** band. Until now the repository said "the cause is closed at
source", which is an assertion. `surface:2` produced the measurement instead,
and this session verified each part independently rather than accepting the
report:

| Claim | How it was checked here | Result |
|---|---|---|
| The offenders predate the fix | read `ts` straight out of `alerts.jsonl` | `scrapfly` `2026-08-23T23:15:00.509Z`, `resend` `2026-08-23T23:44:02.579Z` |
| The fix exists and is dated | `git log -S'announced_from' -- monitor.py` | `cc64abb`, **2026-08-24T08:37:51Z** |
| The gap is real | arithmetic on the two above | ≈ **9 hours** — the lines were written by a build that could not yet have contained the fix |

`surface:2` additionally replayed the full eighteen-hour window under current
code: 30 lines emitted, **zero** with `previous_band == band`, and both
offenders re-derived as `previous_band=None` — correctly, as incident *starts*.
A start has no previous band, and saying so is the fix.

So the audit is naming a defect the current code **provably would not produce**,
against lines that cannot be repaired because the log only grows. That is the
correct behaviour for an append-only record, and it is why the finding is
published rather than cleared.

### The live-versus-replay divergence is now settled, against my earlier claim

Matching shipped alerts to replayed ones on `(rule, provider)`: **30 of 30
matched**, maximum offset **27.3 s**, bounded by the 30 s poll interval. Live and
replay agree on *which* alerts fire and differ only in the instant a sustained
condition is observed to cross. There was never divergence — only evaluation
cadence. This confirms the retraction made at 23:5xZ on 08-23, which was issued
on weaker grounds than this.

**The instructive part is the first attempt.** Keying the comparison on
`(ts, rule, provider)` reported **18 mismatches** and was nearly filed as a
finding. The key was too strict: `ts` is an incidental property of when a
condition was evaluated, not part of an alert's identity. Matching on identity
rather than on an incidental field is the same lesson as excising a trace by
named unit rather than by matched content, and as comparing a projected instant
at the precision it actually carries.

### Shape, not count

`2 of 13` (one caused **solely** by a top-up) → `0 of 12` → `1 of 17` → `2 of 30`.
The class that contradicted `docs/TASK.md` — an alert caused solely by a top-up
or by a reverted blip — has stayed at **zero** while the sample tripled. What
grew is duplicate-suppression residue: quality, not correctness. A rising count
against a tripling sample with the correctness class at zero is convergence, not
drift, and reading the raw count alone would have said the opposite.

## 2026-08-24T11:0xZ — one working session cannot be published, and the reason is a property we chose

`surface:8` cannot export its own working session under `--submission`. Verified
by them, recorded here because `docs/` is this session's zone and the reasoning
should outlive the pane.

Of the 24 blocks carrying a real third-party identifier, excision reaches **9**:
all `tool_result`s. The other 15 are commands they typed and prose they wrote
while diagnosing and fixing the original leak. Excision cannot touch tool inputs
or assistant messages **by design** — that boundary exists so the mode can never
be used to launder a session's own words.

That property is now what blocks the trace, and it is the correct outcome rather
than a bug to route around. The alternatives were all worse: hand-editing
destroys the verbatim guarantee; `--allow-finding` on a real identifier is the
precise act every guard here exists to prevent; weakening the tool at the freeze
for one's own convenience is the override-becomes-routine failure. Not publishing
is the only option that costs nothing but the artifact.

**Task 3's deliverable is unaffected and shipped.** Verified independently here:
`task3-harness-artifact/TRACE.md`, 91,674 bytes, session
`9502fd71-d44d-45eb-aeca-193465d9448b`, exporter header present. The task asks
for a trace of the work; the unpublishable session was the working one, never the
deliverable.

### The fifth unsatisfiable gate, and the first where the artifact is fine

Submission mode is **unsatisfiable for any session that writes the scanner's own
test fixtures.** 9 of the 13 findings are synthetic strings invented as fixtures
— fake user paths, fake token constants — sitting in tool *inputs*, where
excision cannot reach, while `--submission` forbids `--allow-finding`, the one
mechanism for saying "I read this turn and it is a fixture". Publishing those
strings would cost nobody anything.

The other four unsatisfiable gates this run were checks that could not reach a
passing state against correct data. This one is different and worse: the artifact
is genuinely clean and the gate still cannot pass.

**Deliberately not fixed at the freeze.** Changing a guard so one's own trace
passes, at the moment of submission, is the move this project keeps proving
wrong. The shape of a fix, for whoever picks it up: an acknowledgement that names
the specific fixture and is itself recorded in the trace — not a blanket
override.

## 2026-08-24T11:2xZ — the file that exists to catch leaks did not become one

Verified here rather than accepted, because "never tracked in any commit" is
exactly the kind of claim that should be checked:

| Path | Commits touching it, all refs | Blobs at that path in history | Ignored | Tracked |
|---|---|---|---|---|
| `.leak-patterns` | **0** | **0** | yes | no |
| `.DS_Store` | 0 | — | yes | no |
| `.serena` | **3** | 4 files | yes | no *(now)* |

`.leak-patterns` holds the third-party identifiers and has never existed in any
commit on any ref. The instrument built to detect a leak never became one, which
is the outcome the gitignore-plus-never-name-it discipline was for.

**One correction to the sweep, and it is small but it should be exact.**
`.serena` is not "never tracked": four metadata files reached published history
before it was ignored, in `bae8ae2`, `8f68d4e` and `9f354c3` — `.auto_sync_head`,
`.gitignore`, `.serena_sync_state.json` and `project.yml`. Removed from HEAD is
not removed from history on a public repository, so it was worth looking at
rather than assuming.

They are clean. `.serena/memories/` — the knowledge files, the part that could
have carried anything — is **not** among them and was never committed. Scanning
every `.serena` blob across all refs: **0** third-party identifier hits and **0**
absolute paths. `project.yml` is tooling config: project name, language, encoding.

So: no action, and no rewrite. Recorded because "we checked and it was fine" is
only worth something when the check is stated precisely enough to be re-run.

### Why the en dashes survived a sweep, and why the gate stops at markdown

`task1-spend-observability/README.md` held 10 en dashes and **zero** em dashes.
The sweep that cleared em dashes returned clean on it and said nothing about the
file: an em-only check on a file with no em dashes is not evidence of anything.
The gate now matches U+2014 **and** U+2013.

**The dash was not the interesting defect.** Three of the ten were the
estimator's name: `monitor.py` writes `Theil-Sen` with a hyphen, six times, while
its own README wrote it with an en dash three times. Code and documentation had
been spelling the estimator differently and neither looked wrong, because each
was internally consistent. A punctuation sweep surfaced a naming inconsistency
that no reader had caught.

**U+2212 is deliberately exempt.** Seven minus signs remain in that README, which
is the correct character for a negative quantity and matches the `&minus;` the
dashboard renders. Replacing them with hyphens would re-open the code/document
disagreement in the other direction. Verified by running the gate: it matches
U+2014 and U+2013 only.

**The gate stops at markdown, and the reason is not cost.** Extending it to
tracked `.py` is *unsatisfiable*: `tests/test_export_trace.py` asserts
`"Tool call — \`ListAgents\`" in md`, where the em dash is the expected output of
the exporter. Remove it and the test breaks; keep it and the gate fails. That is
the same fixture trap that makes submission mode unsatisfiable for a session
writing the scanner's own fixtures, and adding an exemption mechanism to escape
it is how overrides become routine. `.py` prose was cleared by hand instead, in
docstrings and comments only, never in an assertion or an expected value.

## 2026-08-24T11:3xZ — the two graded links survive a reboot, and the shipped monitor is the running one

Checked because neither property had been verified and both matter to a reader
who opens the links days after we submit.

**The artifact and the demonstration are the same code.** `submission/task1-monitor.py`
and `task1-spend-observability/monitor.py` are the same git blob, and that file's
sha256 matches the copy running on the host. A grader reading the submitted file
is reading what serves the dashboard.

**Neither link depends on a login session or a terminal.** There is no systemd
unit for either, which looks fragile until you check: both run as containers with
`restart=unless-stopped`, so the Docker daemon brings them back after a host
reboot. `/healthz` answers `status: ok` with every provider fresh.

**The separation the T0 decision bought is visible in the uptimes.** The
dashboard container restarted a few hours ago to pick up the `depleted_at`
reconciliation, while `explee-raw-sampler.service` reports `NRestarts=0` across
the whole window. Redeploying what *displays* the data did not disturb what
*captures* it, which is the property that made a clean re-measurement possible
hours after the original design was wrong.

### My own enumeration hazard, committed while checking this

The first probe ran `docker ps` unscoped and returned containers belonging to
unrelated projects on this shared host. That is the exact defect listed in this
session's own watch items, and the correct form was a scoped filter from the
start:

    docker ps --filter name=explee

Recorded rather than quietly re-run, because the catalogue of enumeration
hazards in `AGENTS.md` was built from other people's instances and this one is
mine. The rule is not "be careful with listing commands"; it is *scope every
listing command to this project before running it*, since the contamination
happens at execution and cannot be taken back afterwards.

## 2026-08-24T11:4xZ — the workflow failure was an archived callee, and two dead ends worth keeping

`NDDev-it-com/ci-workflows` was **archived**. GitHub will not serve a reusable
workflow from an archived repository, and every symptom follows from that:
instant failure, **zero jobs created**, no logs to read, and the run registered
under its file path instead of its `name:` field, because nothing ever parsed
the file far enough to find one. Un-archived by the owner; `archived=false`
confirmed here, and all five called workflows resolve at the pinned SHA.

Nothing in this repository was ever wrong.

### The dead ends, recorded because an undocumented one costs the next person a day

**1. Permissions delegation.** The theory was that `permissions: {}` at workflow
level could not delegate `id-token: write` to a job. `surface:8` granted the
union at workflow level, pushed, watched it fail identically, and **reverted
rather than leaving a loosened default under a disproved cause** — the right call
independent of the outcome.

**2. Unresolved pins.** The next theory was that two pinned actions did not
resolve. They were `actions/checkout` and `astral-sh/setup-uv` in `ci.yml`, from
other repositories entirely; looking for them inside `ci-workflows` was a mistake
in where to look, not a finding.

**3. The counterexample that felt decisive and was not.** `dependency-review.yml`
calls the same cross-owner repository at the same pin and had a parsed `name:`,
which appeared to prove cross-owner calls and empty-then-elevate permissions were
both fine. It proves neither: that workflow has **never run**. It is
`pull_request`-triggered and no PR exists, so its `name:` only shows GitHub
*parsed* the file. Parsing is not executing, and only execution touches an
archived repository. A workflow that has never run cannot testify about a
run-time failure.

### What actually settled it

Re-running a previously **successful** scheduled run, unchanged — same run id,
same commit, same event, `run_attempt=2` — and watching it flip from `success` to
`startup_failure`. Nothing in the repository differed between the two attempts,
which located the variable outside the repository and left one API call to find
it. The lesson generalises: when a thing that used to work stops, re-run the
identical thing before theorising about what changed in your files.

### Both workflows now declare `workflow_dispatch`

GitHub refuses to retry a run that failed at startup, and neither workflow had a
manual trigger, so the only way to re-test was to push. A diagnosis should not
cost commits.

### Un-archiving was necessary and not sufficient: Actions stayed disabled

The first push after un-archiving produced the identical signature — both
workflows failed with **zero jobs created**. The archive was therefore half the
answer, and the other half is one field on the callee:

    gh api repos/NDDev-it-com/ci-workflows/actions/permissions   ->  {"enabled": false}

**Archiving a repository disables its Actions; un-archiving does not re-enable
them.** A repository whose Actions are disabled cannot serve a reusable workflow,
which produces exactly the same symptoms as the archive did. Two distinct causes,
one signature, and the second was invisible until the first was cleared.

Everything else about the call was verified intact at that moment: the pin still
declares `on: workflow_call`, all five called files resolve at it, and it remains
reachable from the callee's default branch. So the remaining fix is a single
setting on a repository in another organisation, which is not ours to change.

**The method note worth keeping:** clearing one cause and re-testing is what
exposed the second. Had the fix been applied together with anything else, the
still-failing result would have been ambiguous between "the archive was not the
cause" and "the archive was one of two causes". Change one thing, re-run the same
thing, read the signature.

## 2026-08-24T11:5xZ — a "safe" mechanical sweep with a 12% damage rate

Two sessions swept dashes independently and both measured what a blanket
dash-to-comma rule actually did:

| Session | Replacements | Comma splices created | Damage rate |
|---|---|---|---|
| `surface:5` (Task 2) | ~80 | **10** | 12% |
| `surface:8` (AGENTS, Task 3) | 44 | **14** | **32%** |

A rule anyone would have called safe damaged between one line in eight and one in
three, and it traded a machine-text tell for a grammatical error, which is the
worse defect because it is harder to see. This repository had already shipped
`decline , recorded` from exactly this. Every splice was repaired by reading the
sentence, not by a second rule.

That is the number behind the instruction "rewrite the sentence where the dash
carried it". It was written as a style preference and it is really a correctness
requirement.

**One dash is deliberate and must survive the documentation pass.**
`task2-stt-benchmark/docs/reference-policy.md` rule R7 defines how a false start
is transcribed, and its worked example carries a dash marking the point where the
speaker cuts themselves off: `*«мы ре— мы решили»*`. That dash is **data**.
Removing it corrupts the example that defines the rule. It is annotated inline,
and it is outside the dash gate's scope — checked, not assumed. Had that gate
been scoped to "all tracked markdown" it would have been the second check in this
run whose only passing state is corrupting a record.

### `git commit -m "…"` executes anything between backticks

`surface:5` lost two quotations from a commit message this way: backticked
identifiers inside a double-quoted shell string are command substitution, and the
shell replaced them with the empty output of the commands it ran. The code in
that commit was unaffected; only the message lost text.

Confirmed here directly rather than taken on report:

    "a `echo SUBSTITUTED` b"   ->  a SUBSTITUTED b
    'a `echo SUBSTITUTED` b'   ->  a `echo SUBSTITUTED` b

This repository writes long commit messages full of backticked identifiers, so
the hazard is live for every session. A heredoc into `git commit -F -` is immune.

They corrected the record in a **follow-up commit rather than amending**, which
is right: amending a pushed commit means a force push, and three sessions are
working in this tree while the repository is published. A wrong message plus a
correction is cheaper than a history rewrite nobody expected.
