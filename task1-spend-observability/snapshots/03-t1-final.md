# Window snapshot 03: t1-final

Immutable record of the observation window.

The collector was still writing when this was taken, so verification is
by prefix: the file was copied down, the copy hashed, and the host asked
for the digest of the same leading byte count. A match proves the
measurements below describe the exact bytes the collector wrote. The log
is append-only, which is what makes a prefix the right thing to check.

Read-only. Nothing was restarted and nothing was written on the host.
This window cannot be recreated, and no snapshot is worth risking it.

| | |
|---|---|
| snapshot | **03** in the six-hourly sequence |
| taken at | `2026-08-23T22:55:09Z` |
| label | `t1-final` |
| repository | `3398f0a` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `68fd0794f91c8a169adb04299c66cdf7da659e82efc21407916580d854e6df4e` |
| sha256 of the same leading bytes on the host | `68fd0794f91c8a169adb04299c66cdf7da659e82efc21407916580d854e6df4e` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 7,152,935 bytes |
| lines | 12,848 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-23T22:54:46.642000Z` |
| span | **6.6889 h** (24,080 s) |
| six hours reached | **yes** |
| records | 12,848 |
| malformed records | **0** |
| providers seen | 15 |

## Continuity

A gap is the only thing that could invalidate a window that cannot be
recreated, so it is measured rather than asserted.

| | |
|---|---|
| largest gap between cycles | **29.7 s** |
| at | `2026-08-23T21:14:41.869000Z` |
| largest gap for any single provider | 32.0 s |

## Response classes observed

| class | count |
|---|---:|
| `http_429` | 359 |
| `http_500` | 203 |
| `http_503` | 274 |
| `http_504` | 181 |
| `ok_or_schema_miss` | 11,028 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
