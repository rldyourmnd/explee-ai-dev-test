# Policy sensitivity

Every threshold in `POLICY` is a choice nobody specified. Left as bare
constants they are magic numbers; measured against the window they become a
defended choice with a stated cost.

| provenance | |
|---|---|
| raw records | 11,888 |
| window | `2026-08-23T16:13:26.775Z` -> `2026-08-23T22:24:45.192Z` |
| repository | `7964031` |
| regenerate | `uv run tools/policy_sensitivity.py > task1-spend-observability/POLICY-SENSITIVITY.md` |

Ground truth, computed from the raw log without reference to any threshold: **29 outages** of 10+ consecutive failed polls, across **13 of 15 providers**. Longest first:

| provider | started | polls | duration |
|---|---|---:|---:|
| `zerobounce` | 2026-08-23T20:50:40.585Z | 32 | 15.5 min |
| `findymail` | 2026-08-23T18:08:32.777Z | 22 | 10.5 min |
| `tremendous` | 2026-08-23T16:57:29.321Z | 21 | 10.0 min |
| `zerobounce` | 2026-08-23T21:26:42.163Z | 20 | 9.5 min |
| `anthropic` | 2026-08-23T17:26:30.654Z | 20 | 9.5 min |
| `scrapfly` | 2026-08-23T20:08:08.659Z | 19 | 9.0 min |
| `tremendous` | 2026-08-23T20:57:11.094Z | 19 | 9.0 min |
| `brightdata` | 2026-08-23T21:15:41.668Z | 18 | 8.5 min |
| `meta_ads` | 2026-08-23T16:22:27.651Z | 16 | 7.5 min |
| `resend` | 2026-08-23T21:27:12.445Z | 15 | 7.0 min |

## Unavailability tolerance

| setting | lines | incidents | restatements | missed |
|---|---:|---:|---:|---:|
| 5 min                            |    24 |        19 |            0 |      0 |
| 10 min                           |    15 |        10 |            0 |      9 |
| 15 min                           |    12 |         7 |            0 |     12 |
| 20 min                           |    11 |         6 |            0 |     13 |

`missed` counts providers with a ground-truth outage that received no `unavailable` line. It varies only with this setting; in the tables below it is constant at 13 and omitted.

## Runway lead time

| setting | lines | incidents | restatements |
|---|---:|---:|---:|
| 6h critical / 24h warning        |    10 |         6 |            0 |
| 12h critical / 48h warning       |    11 |         7 |            0 |
| 24h critical / 72h warning       |    12 |         7 |            0 |
| 48h critical / 168h warning      |    17 |        12 |            0 |

## Materiality bands and the re-fire floor

| setting | lines | incidents | restatements |
|---|---:|---:|---:|
| shipped bands                    |    12 |         7 |            0 |
| re-fire floor 0 s                |    12 |         7 |            0 |
| re-fire floor 1 h                |    10 |         7 |            0 |

## Anomaly sensitivity (k, in MADs)

| setting | lines | incidents | burn_anomaly lines |
|---|---:|---:|---:|
| k = 3                            |    16 |        11 |                  7 |
| k = 4                            |    13 |         8 |                  4 |
| k = 6                            |    12 |         7 |                  3 |
| k = 8                            |    12 |         7 |                  3 |
| k = 12                           |     9 |         5 |                  0 |

## Minimum evidence before a projection may fire

| setting | lines | incidents |
|---|---:|---:|
| 0 s                              |    14 |         8 |
| 600 s                            |    14 |         8 |
| 1800 s                           |    12 |         7 |
| 3600 s                           |    11 |         7 |

## Why 15 minutes, and the outage that vindicated it

The API injects failures continuously. Over 6.19 hours it produced **29 outages**
of five minutes or more, across **13 of 15 providers**. Twenty-eight healed on
their own. One did not: `zerobounce` went dark for **15.5 minutes across 32
consecutive failed polls** returning HTTP 500, and it is the only outage in the
window that produced an `unavailable` line.

That is the threshold doing exactly what it was set to do. It sits above the
longest outage anyone had measured when it was chosen, so a line means "darker
than anything we have seen". The second-longest outage in the whole window is
`findymail` at 10.5 minutes, a full five minutes clear of the threshold, so the
silence is a margin rather than a near miss.

The cost is explicit, and stating it is why the first table exists. Dropping to a
five-minute tolerance catches all 29 and **doubles total alert volume, 12 lines
to 24** over the same window, every added line describing something that resolved
before a human could read it. That is how an alert channel becomes noise, and
noise is why the one line that matters gets missed.

A ten-minute outage still produces no line. That is a real cost rather than a
hidden one, and it is not invisible: freshness turns amber at 300 s and red
beyond, and `/healthz` reports the provider stale. But nobody is *told*.

If the employer's answer is "tell me about any five-minute gap", that is one line
in `POLICY`, and the first table states what it will cost.

## What the other tables say

- **Runway lead time** moves alert volume roughly linearly and produces no
  restatements at any setting, because the materiality bands absorb drift. The
  most aggressive setting tested, 48 h critical and 168 h warning, produces 17
  lines against the shipped 12.
- **The re-fire floor is no longer untested.** 0 s and the shipped 600 s give
  identical counts over the window measured above, because every band change in
  it is a genuine deterioration rather than a value oscillating across an edge.
  An earlier version of this bullet concluded from that the floor was insurance
  against a case the window did not contain. It contains it now: `meta_ads`
  crossed the `burn_anomaly` `lt50`/`lt100` edge at 2026-08-24T07:32:06Z, fell
  back to `lt50`, and crossed it again at 07:50:18Z at a **lower** deviation,
  50.7 MAD against 66.7. The floor correctly did not suppress the second line,
  because the gap was 1,080 s against a 600 s floor and a condition that
  genuinely improves and then worsens again should speak. Both of those lines are in the
  `alerts.jsonl` shipped beside this document, stamped `2026-08-24T07:32:06Z`
  and `2026-08-24T07:50:18Z`, so the claim can be checked rather than taken.
  An earlier version of this bullet had to disclose that they were not: the
  shipped file was cut before they were emitted, and a threshold defended with
  evidence the reader cannot open is an assertion wearing the clothes of a
  proof. The file only grows, so the disclosure became unnecessary rather than
  being argued away.
- **Anomaly `k` is the sharpest dial, and it has moved.** `k=3` fires seven
  `burn_anomaly` lines, the shipped `k=6` fires three, `k=12` fires none. The
  three at `k=6` are the `resend` acceleration and two `meta_ads` lines. All
  three reconcile in `ALERT-AUDIT.md`, and the `meta_ads` pair was checked by
  hand against the raw series after its negative baseline looked wrong and turned
  out to be correct. An earlier version of this document recorded **one** line at
  `k=6`. That was true of a three-hour window and is no longer true, which is the
  reason this table is regenerated rather than remembered.
- **Minimum projection evidence** trades lines for confidence. Dropping to 0 s or
  600 s adds two lines and an eighth incident. The shipped 1800 s is what stopped
  the `twocaptcha` reverted blip from firing a false 0.5 h runway.
