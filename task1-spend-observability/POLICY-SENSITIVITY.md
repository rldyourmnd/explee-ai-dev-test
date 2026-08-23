# Policy sensitivity

Every threshold in `POLICY` is a choice nobody specified. This is what each
choice costs on the captured window, so the numbers in `README.md` are defended
by a table rather than by an argument. Reproduce with
`monitor.py --once` against a modified `POLICY`; the generating script is in the
session trace.

**The finding that matters most is the first table.** With the shipped
unavailability tolerance of 15 minutes, *no unavailability alert fires in this
window at all* — deliberately. See the note under that table before reading it
as a miss.


Ground truth, computed from the raw log independently of any threshold: 15 outages of 10+ consecutive failed polls (>=5 min), across 10 providers.

  findymail    2026-08-23T18:08:32.777Z  22 polls   10.5 min
  tremendous   2026-08-23T16:57:29.321Z  21 polls   10.0 min
  anthropic    2026-08-23T17:26:30.654Z  20 polls    9.5 min
  meta_ads     2026-08-23T16:22:27.651Z  16 polls    7.5 min
  brightdata   2026-08-23T18:15:33.064Z  15 polls    7.0 min
  tremendous   2026-08-23T17:28:30.828Z  15 polls    7.0 min
  evomi        2026-08-23T18:35:03.999Z  14 polls    6.5 min
  twocaptcha   2026-08-23T18:06:32.561Z  13 polls    6.0 min
  findymail    2026-08-23T16:18:27.314Z  13 polls    6.0 min
  bounceban    2026-08-23T16:19:27.385Z  13 polls    6.0 min

## Unavailability tolerance

| setting | lines | incidents | restatements | missed | missed providers |
|---|---:|---:|---:|---:|---|
| unavailable_alert_s = 5 min        |    26 |        17 |            5 |      0 | — |
| unavailable_alert_s = 10 min       |    14 |        10 |            0 |      7 | bounceban, brightdata, evomi, meta_ads, scrapfly, twocaptcha, zerobounce |
| unavailable_alert_s = 15 min       |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| unavailable_alert_s = 20 min       |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| unavailable_alert_s = 30 min       |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |

## Runway lead time

| setting | lines | incidents | restatements | missed | missed providers |
|---|---:|---:|---:|---:|---|
| runway 6h crit / 24h warn          |     9 |         6 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| runway 12h crit / 48h warn         |    10 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| runway 24h crit / 72h warn         |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| runway 48h crit / 168h warn        |    15 |        11 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |

## Materiality bands versus a plain cooldown

| setting | lines | incidents | restatements | missed | missed providers |
|---|---:|---:|---:|---:|---|
| selected bands (shipped)           |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| re-fire floor 0 s                  |    11 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |
| re-fire floor 1 h                  |     9 |         7 |            0 |     10 | anthropic, bounceban, brightdata, evomi, findymail, meta_ads, scrapfly, tremendous, twocaptcha, zerobounce |

## Anomaly sensitivity (k, in MADs)

| setting | lines | incidents | restatements | burn_anomaly lines |
|---|---:|---:|---:|---:|
| anomaly_k = 3.0                    |    14 |        10 |            0 |                  4 |
| anomaly_k = 4.0                    |    12 |         8 |            0 |                  2 |
| anomaly_k = 6.0                    |    11 |         7 |            0 |                  1 |
| anomaly_k = 8.0                    |    11 |         7 |            0 |                  1 |
| anomaly_k = 12.0                   |    10 |         6 |            0 |                  0 |

## Minimum evidence before a projection may fire

| setting | lines | incidents | restatements |
|---|---:|---:|---:|
| min_projection_span_s = 0          |    12 |         7 |            0 |
| min_projection_span_s = 600        |    12 |         7 |            0 |
| min_projection_span_s = 1800       |    11 |         7 |            0 |
| min_projection_span_s = 3600       |     8 |         5 |            0 |

## Reading the "missed" column

`missed` counts providers that had a ground-truth outage — 10 or more
consecutive failed polls, computed from the raw log without reference to any
threshold — and received no `unavailable` line. It only varies with the
unavailability tolerance; in the runway, band and anomaly tables it is constant
and should be ignored, because those settings do not touch that rule.

## Why 15 minutes, given it misses all 15 outages

This is the trade-off the table exists to make visible, not a defect hidden by
one.

The API injects failures continuously: **15 outages of 5+ minutes across 10 of
15 providers in under three hours**, none lasting beyond 10.5 minutes, every one
self-healing. A 5-minute tolerance catches all of them at a cost of **26 lines**
— roughly eight an hour — for conditions that resolve before anyone could read
the line, let alone act on it. That is how an alert channel becomes noise, and
the reason the channel then fails to convey the one line that matters.

The shipped setting sits above the longest outage ever observed, so it fires
only when a provider is darker than anything measured. The cost is explicit: a
ten-minute outage produces no line. It is not invisible — the dashboard shows
freshness turning amber at 300 s and red past that, and `/healthz` reports the
provider stale — but nobody is *told*.

If the employer's answer is "tell me about any five-minute gap", the setting is
one line in `POLICY` and this table says what it will cost: 26 lines instead of
11, with 5 of them restatements.

## What the other tables say

- **Runway lead time** is close to linear in alert volume: 6h/24h gives 9 lines,
  48h/168h gives 15. No setting in the range produces restatements, because the
  materiality bands absorb drift.
- **The re-fire floor barely matters** on this window: 0 s and the shipped 600 s
  both give 11 lines, because band changes here are genuine deteriorations
  spaced minutes apart rather than a value oscillating across an edge. The floor
  is insurance against a case this window does not contain.
- **Anomaly `k`** is the sharpest dial. `k=3` produces 4 `burn_anomaly` lines,
  `k=6` produces 1, `k=12` produces none. The single line at the shipped `k=6`
  is the genuine `resend` acceleration, which was verified by hand against the
  raw series. `k=3` would have added three more that the window does not
  justify.
- **Minimum projection evidence** trades lines for confidence: 0 s gives 12
  lines, 1800 s gives 11, 3600 s gives 8. The shipped 1800 s is what stopped the
  `twocaptcha` reverted-blip from firing a false 0.5 h runway.
