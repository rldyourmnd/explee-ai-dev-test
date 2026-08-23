# Alert audit

Every line in `alerts.jsonl` re-derived from the raw records around its
timestamp: the value quoted, the rate quoted, the sustain claimed, the raw
readings either side, and whether a top-up, package reset or reverted blip sat
within 30 minutes close enough to explain the line away.

Regenerate with `python3 monitor.py --audit --raw data/raw_samples.jsonl`;
it exits non-zero if any line fails to reconcile.

| provenance | |
|---|---|
| alert lines | 11 |
| raw records | 6,960 |
| repository | `4ac8d73` |
| result | **0 unreconciled** |

## Every line

| # | when | rule | provider | headline | band | reconciled |
|---:|---|---|---|---:|---|---|
| 1 | 2026-08-23T16:48:58.531Z | `package_exhaustion` | `elevenlabs` | 44.0 h | `package_exhaustion:lt48` | yes |
| 2 | 2026-08-23T16:48:58.531Z | `package_exhaustion` | `resend` | 182.0 h | `package_exhaustion:ge168` | yes |
| 3 | 2026-08-23T16:48:58.531Z | `package_exhaustion` | `scrapfly` | 134.9 h | `package_exhaustion:lt168` | yes |
| 4 | 2026-08-23T16:48:58.531Z | `runway` | `openrouter` | 55.6 h | `runway:warning:lt72` | yes |
| 5 | 2026-08-23T17:00:29.033Z | `package_exhaustion` | `findymail` | 186.0 h | `package_exhaustion:ge168` | yes |
| 6 | 2026-08-23T17:07:59.407Z | `burn_anomaly` | `resend` | 20.4 MAD | `burn_anomaly:lt50` | yes |
| 7 | 2026-08-23T17:08:59.455Z | `package_exhaustion` | `resend` | 157.1 h | `package_exhaustion:lt168` | yes |
| 8 | 2026-08-23T17:22:30.111Z | `package_exhaustion` | `resend` | 71.8 h | `package_exhaustion:lt72` | yes |
| 9 | 2026-08-23T17:44:01.213Z | `package_exhaustion` | `resend` | 47.8 h | `package_exhaustion:lt48` | yes |
| 10 | 2026-08-23T18:03:32.259Z | `runway` | `openrouter` | 47.9 h | `runway:warning:lt48` | yes |
| 11 | 2026-08-23T18:44:34.368Z | `package_exhaustion` | `bounceban` | 180.4 h | `package_exhaustion:ge168` | yes |

Distinct (rule, provider, band) triples: **11** across 11 lines. Repeated triples: **0** — a repeat is what a restatement would look like.

## The `resend` sequence (4 lines) — deterioration, not spam

Repeated lines for one provider invite the suspicion that the rule is restating
itself. It is not: each line crosses a materiality band the previous one did not,
and the projection genuinely collapsed underneath them.

| when | runway | band | remaining | burn |
|---|---:|---|---:|---:|
| 2026-08-23T16:48:58.531Z | 182.0 h | `package_exhaustion:ge168` | 41,233 | 227/h |
| 2026-08-23T17:08:59.455Z | 157.1 h | `package_exhaustion:lt168` | 40,905 | 260/h |
| 2026-08-23T17:22:30.111Z | 71.8 h | `package_exhaustion:lt72` | 40,626 | 566/h |
| 2026-08-23T17:44:01.213Z | 47.8 h | `package_exhaustion:lt48` | 40,207 | 840/h |

Runway fell from **182.0 h** to **47.8 h** while burn rose from **227** to **840 credits/h**. Four lines over an hour for a provider
whose time-to-exhaustion shrank fourfold is the rule working, and every band appears
exactly once.

## Top-up-only incidents

**0.** A top-up, package reset or reverted blip is normal operations and is recorded
as an event, never as an alert. The audit prints any event within 30 minutes of a
line so a reader can check that judgement instead of taking it.

## Full reconciliation output

```
[replay] 6960 records in 21.0s from task1-spend-observability/data/raw_samples.jsonl
Audit of 11 alert lines against the raw window

[1] 2026-08-23T16:48:58.531Z  warning  package_exhaustion  elevenlabs
     text: elevenlabs (Deepgram) is projected to exhaust its credits package 44.0 h from now, 199.2 h before the 2026-09-01 refresh; 867,131 of 1,000,000 credits
     re-derived at that instant: value=867131.0 burn=19708.782880354185 runway_h=43.997186699152316
       raw 2026-08-23T16:47:58.861Z state=ok http=200 value=867301.0
       raw 2026-08-23T16:48:28.873Z state=ok http=200 value=867131.0
       raw 2026-08-23T16:48:58.880Z state=ok http=200 value=866960.0
       raw 2026-08-23T16:49:28.928Z state=ok http=200 value=866790.0
     reconciled

[2] 2026-08-23T16:48:58.531Z  warning  package_exhaustion  resend
     text: resend (Resend) is projected to exhaust its credits package 182.0 h from now, 199.2 h before the 2026-09-01 refresh; 41,233 of 50,000 credits left, bu
     re-derived at that instant: value=41233.0 burn=226.55171317417714 runway_h=182.00259632686735
       raw 2026-08-23T16:47:58.923Z state=ok http=200 value=41235.0
       raw 2026-08-23T16:48:28.931Z state=ok http=200 value=41233.0
       raw 2026-08-23T16:48:58.953Z state=ok http=200 value=41231.0
       raw 2026-08-23T16:49:28.962Z state=ok http=200 value=41229.0
     reconciled

[3] 2026-08-23T16:48:58.531Z  warning  package_exhaustion  scrapfly
     text: scrapfly (ScraperAPI) is projected to exhaust its credits package 134.9 h from now, 199.2 h before the 2026-09-01 refresh; 34,533 of 50,000 credits le
     re-derived at that instant: value=34533.0 burn=256.00864164191194 runway_h=134.88997784810127
       raw 2026-08-23T16:47:58.653Z state=ok http=200 value=34535.0
       raw 2026-08-23T16:48:28.659Z state=ok http=200 value=34533.0
       raw 2026-08-23T16:48:58.669Z state=ok http=200 value=34530.0
       raw 2026-08-23T16:49:28.707Z state=ok http=200 value=34528.0
     reconciled

[4] 2026-08-23T16:48:58.531Z  warning  runway  openrouter
     text: openrouter (Groq, prepaid_balance) reaches zero in 55.6 h at the observed burn of 4.52 USD/h; 251.28 USD left, projected 2026-08-26T00:22:45.676Z
     re-derived at that instant: value=251.28 burn=4.522426186568981 runway_h=55.56309592100563
       raw 2026-08-23T16:47:58.806Z state=ok http=200 value=251.31
       raw 2026-08-23T16:48:28.812Z state=ok http=200 value=251.28
       raw 2026-08-23T16:48:58.826Z state=schema_miss http=200 value=None
       raw 2026-08-23T16:49:28.848Z state=ok http=200 value=251.21
     reconciled

[5] 2026-08-23T17:00:29.033Z  warning  package_exhaustion  findymail
     text: findymail (Hunter) is projected to exhaust its credits package 186.0 h from now, 199.0 h before the 2026-09-01 refresh; 10,295 of 12,000 credits left,
     re-derived at that instant: value=10295.0 burn=55.33949241387791 runway_h=186.03350972222222
       raw 2026-08-23T16:59:29.208Z state=ok http=200 value=10295.0
       raw 2026-08-23T16:59:59.269Z state=ok http=200 value=10295.0
       raw 2026-08-23T17:00:29.285Z state=http_error http=429 value=None
       raw 2026-08-23T17:00:59.296Z state=ok http=200 value=10294.0
     reconciled

[6] 2026-08-23T17:07:59.407Z  warning  burn_anomaly  resend
     text: resend (Resend) burn accelerated to 729 credits/h over the last 30 min against a window baseline of 240 credits/h (3.0x); deviation 20.4 MAD-equivalen
     re-derived at that instant: value=40925.0 burn=239.89604504714566 runway_h=170.59472569444486
       raw 2026-08-23T17:06:59.802Z state=ok http=200 value=40935.0
       raw 2026-08-23T17:07:29.779Z state=ok http=200 value=40925.0
       raw 2026-08-23T17:07:59.807Z state=ok http=200 value=40915.0
       raw 2026-08-23T17:08:29.820Z state=ok http=200 value=40905.0
     reconciled

[7] 2026-08-23T17:08:59.455Z  warning  package_exhaustion  resend
     text: resend (Resend) is projected to exhaust its credits package 157.1 h from now, 198.9 h before the 2026-09-01 refresh; 40,905 of 50,000 credits left, bu
     re-derived at that instant: value=40905.0 burn=260.4232885129517 runway_h=157.07120601069312
       raw 2026-08-23T17:07:59.807Z state=ok http=200 value=40915.0
       raw 2026-08-23T17:08:29.820Z state=ok http=200 value=40905.0
       raw 2026-08-23T17:08:59.840Z state=ok http=200 value=40895.0
       raw 2026-08-23T17:09:29.887Z state=ok http=200 value=40885.0
     reconciled

[8] 2026-08-23T17:22:30.111Z  warning  package_exhaustion  resend
     text: resend (Resend) is projected to exhaust its credits package 71.8 h from now, 198.6 h before the 2026-09-01 refresh; 40,626 of 50,000 credits left, bur
     re-derived at that instant: value=40626.0 burn=565.8933089937516 runway_h=71.7909177477986
       raw 2026-08-23T17:21:30.513Z state=ok http=200 value=40636.0
       raw 2026-08-23T17:22:00.542Z state=ok http=200 value=40626.0
       raw 2026-08-23T17:22:30.506Z state=ok http=200 value=40615.0
       raw 2026-08-23T17:23:00.518Z state=ok http=200 value=40605.0
     reconciled

[9] 2026-08-23T17:44:01.213Z  warning  package_exhaustion  resend
     text: resend (Resend) is projected to exhaust its credits package 47.8 h from now, 198.3 h before the 2026-09-01 refresh; 40,207 of 50,000 credits left, bur
     re-derived at that instant: value=40207.0 burn=840.4568027889542 runway_h=47.83946047741887
       raw 2026-08-23T17:43:01.566Z state=ok http=200 value=40216.0
       raw 2026-08-23T17:43:31.703Z state=ok http=200 value=40207.0
       raw 2026-08-23T17:44:01.634Z state=ok http=200 value=40199.0
       raw 2026-08-23T17:44:31.649Z state=ok http=200 value=40190.0
     reconciled

[10] 2026-08-23T18:03:32.259Z  warning  runway  openrouter
     text: openrouter (Groq, prepaid_balance) reaches zero in 47.9 h at the observed burn of 5.10 USD/h; 243.99 USD left, projected 2026-08-25T17:56:22.377Z
     re-derived at that instant: value=243.99 burn=5.095802029756428 runway_h=47.88058848739506
       raw 2026-08-23T18:02:32.484Z state=ok http=200 value=244.05
       raw 2026-08-23T18:03:02.522Z state=ok http=200 value=243.99
       raw 2026-08-23T18:03:32.568Z state=ok http=200 value=243.93
       raw 2026-08-23T18:04:02.598Z state=ok http=200 value=243.87
     reconciled

[11] 2026-08-23T18:44:34.368Z  warning  package_exhaustion  bounceban
     text: bounceban (Kickbox) is projected to exhaust its credits package 180.4 h from now, 197.3 h before the 2026-09-01 refresh; 6,779 of 8,000 credits left, 
     re-derived at that instant: value=6779.0 burn=37.58024949110079 runway_h=180.38730694444445
       raw 2026-08-23T18:43:34.602Z state=ok http=200 value=6780.0
       raw 2026-08-23T18:44:04.621Z state=ok http=200 value=6779.0
       raw 2026-08-23T18:44:34.647Z state=ok http=200 value=6779.0
       raw 2026-08-23T18:45:04.664Z state=ok http=200 value=6779.0
     nearby event: top_up at 2026-08-23T19:00:05.490Z delta=4.0
     note: a normal-operations event sits within 30 min; the line is a projection, not a reaction to it
     reconciled

unreconciled lines: 0 of 11
```
