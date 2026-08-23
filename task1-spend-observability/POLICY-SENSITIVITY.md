# Policy sensitivity

Every threshold in `POLICY` is a choice nobody specified. Left as bare
constants they are magic numbers; measured against the window they become a
defended choice with a stated cost.

| provenance | |
|---|---|
| raw records | 6,112 |
| window | `2026-08-23T16:13:26.775Z` -> `2026-08-23T19:24:06.735Z` |
| repository | `ce6fe1c` |
| regenerate | `uv run tools/policy_sensitivity.py` |

Ground truth, computed from the raw log without reference to any threshold: **16 outages** of 10+ consecutive failed polls, across **10 of 15 providers**. Longest first:

| provider | started | polls | duration |
|---|---|---:|---:|
| `findymail` | 2026-08-23T18:08:32.777Z | 22 | 10.5 min |
| `tremendous` | 2026-08-23T16:57:29.321Z | 21 | 10.0 min |
| `anthropic` | 2026-08-23T17:26:30.654Z | 20 | 9.5 min |
| `meta_ads` | 2026-08-23T16:22:27.651Z | 16 | 7.5 min |
| `brightdata` | 2026-08-23T18:15:33.064Z | 15 | 7.0 min |
| `tremendous` | 2026-08-23T17:28:30.828Z | 15 | 7.0 min |
| `evomi` | 2026-08-23T18:35:03.999Z | 14 | 6.5 min |
| `twocaptcha` | 2026-08-23T18:06:32.561Z | 13 | 6.0 min |
| `findymail` | 2026-08-23T16:18:27.314Z | 13 | 6.0 min |
| `bounceban` | 2026-08-23T16:19:27.385Z | 13 | 6.0 min |

## Unavailability tolerance

| setting | lines | incidents | restatements | missed |
|---|---:|---:|---:|---:|
| 5 min                            |    27 |        17 |            6 |      0 |
| 10 min                           |    14 |        10 |            0 |      7 |
| 15 min                           |    11 |         7 |            0 |     10 |
| 20 min                           |    11 |         7 |            0 |     10 |

`missed` counts providers with a ground-truth outage that received no `unavailable` line. It varies only with this setting; in the tables below it is constant at 10 and omitted.

## Runway lead time

| setting | lines | incidents | restatements |
|---|---:|---:|---:|
| 6h critical / 24h warning        |     9 |         6 |            0 |
| 12h critical / 48h warning       |    10 |         7 |            0 |
| 24h critical / 72h warning       |    11 |         7 |            0 |
| 48h critical / 168h warning      |    16 |        11 |            1 |

## Materiality bands and the re-fire floor

| setting | lines | incidents | restatements |
|---|---:|---:|---:|
| shipped bands                    |    11 |         7 |            0 |
| re-fire floor 0 s                |    11 |         7 |            0 |
| re-fire floor 1 h                |     9 |         7 |            0 |

## Anomaly sensitivity (k, in MADs)

| setting | lines | incidents | burn_anomaly lines |
|---|---:|---:|---:|
| k = 3                            |    14 |        10 |                  4 |
| k = 4                            |    12 |         8 |                  2 |
| k = 6                            |    11 |         7 |                  1 |
| k = 8                            |    11 |         7 |                  1 |
| k = 12                           |    10 |         6 |                  0 |

## Minimum evidence before a projection may fire

| setting | lines | incidents |
|---|---:|---:|
| 0 s                              |    12 |         7 |
| 600 s                            |    12 |         7 |
| 1800 s                           |    11 |         7 |
| 3600 s                           |     8 |         5 |

## Why 15 minutes, when it misses every outage in the window

This is the trade-off the table exists to make visible, not a defect it hides.

The API injects failures continuously. Over three hours it produced **16 outages
of five minutes or more across 10 of 15 providers**, none lasting beyond 10.5
minutes, every one self-healing. A five-minute tolerance catches all of them, at
a cost of roughly **eight lines an hour** describing conditions that resolve
before anyone could read the line, let alone act on it. That is how an alert
channel becomes noise, and noise is why the one line that matters gets missed.

The shipped setting sits above the longest outage ever observed, so a line means
"darker than anything we have measured". The cost is explicit: a ten-minute
outage produces no line. It is not invisible — freshness turns amber at 300 s
and red beyond, and `/healthz` reports the provider stale — but nobody is *told*.

If the employer's answer is "tell me about any five-minute gap", that is one
line in `POLICY`, and the first table states what it will cost.

## What the other tables say

- **Runway lead time** moves alert volume roughly linearly and produces no
  restatements at any setting, because the materiality bands absorb drift.
- **The re-fire floor barely matters here.** 0 s and the shipped 600 s give the
  same count, because band changes in this window are genuine deteriorations
  minutes apart rather than a value oscillating across an edge. The floor is
  insurance against a case this window does not contain.
- **Anomaly `k` is the sharpest dial.** `k=3` fires four `burn_anomaly` lines,
  `k=6` one, `k=12` none. The single line at the shipped `k=6` is the genuine
  `resend` acceleration, checked by hand against the raw series; `k=3` adds three
  the window does not justify.
- **Minimum projection evidence** trades lines for confidence. The shipped
  1800 s is what stopped the `twocaptcha` reverted blip from firing a false
  0.5 h runway.
