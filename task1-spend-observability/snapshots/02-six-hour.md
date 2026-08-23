# Window snapshot 02 — six-hour

Immutable record of the observation window.

The collector was still writing when this was taken, so verification is
by prefix: the file was copied down, the copy hashed, and the host asked
for the digest of the same leading byte count. A match proves the
measurements below describe the exact bytes the collector wrote. The log
is append-only, which is what makes a prefix the right thing to check.

Read-only. Nothing was restarted and nothing was written on the host —
this window cannot be recreated, and no snapshot is worth risking it.

| | |
|---|---|
| snapshot | **02** in the six-hourly sequence |
| taken at | `2026-08-23T22:15:03Z` |
| label | `six-hour` |
| repository | `f9b1728` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `349f0cabbbe2f42c0825774b8352c64e043c24b7d1088d8c8ccf95763d051e68` |
| sha256 of the same leading bytes on the host | `349f0cabbbe2f42c0825774b8352c64e043c24b7d1088d8c8ccf95763d051e68` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 6,413,566 bytes |
| lines | 11,568 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-23T22:14:44.654000Z` |
| span | **6.0216 h** (21,678 s) |
| six hours reached | **yes** |
| records | 11,568 |
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
| `http_429` | 320 |
| `http_500` | 185 |
| `http_503` | 247 |
| `http_504` | 159 |
| `ok_or_schema_miss` | 9,934 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
