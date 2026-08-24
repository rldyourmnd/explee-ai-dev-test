# Window snapshot 05 - eighteen-hour

Immutable record of the observation window.

The collector was still writing when this was taken, so verification is
by prefix: the file was copied down, the copy hashed, and the host asked
for the digest of the same leading byte count. A match proves the
measurements below describe the exact bytes the collector wrote. The log
is append-only, which is what makes a prefix the right thing to check.

Read-only. Nothing was restarted and nothing was written on the host -
this window cannot be recreated, and no snapshot is worth risking it.

| | |
|---|---|
| snapshot | **05** in the six-hourly sequence |
| taken at | `2026-08-24T10:14:15Z` |
| label | `eighteen-hour` |
| repository | `8d2b432` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `9e08a9e0e1f307f5f7e0e325cf8b010328dbc824e1d4625fee51ab912c816bbe` |
| sha256 of the same leading bytes on the host | `9e08a9e0e1f307f5f7e0e325cf8b010328dbc824e1d4625fee51ab912c816bbe` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 19,020,910 bytes |
| lines | 34,560 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-24T10:13:50.212000Z` |
| span | **18.0065 h** (64,823 s) |
| six hours reached | **yes** |
| records | 34,560 |
| malformed records | **0** |
| providers seen | 15 |

## Continuity

A gap is the only thing that could invalidate a window that cannot be
recreated, so it is measured rather than asserted.

| | |
|---|---|
| largest gap between cycles | **29.7 s** |
| at | `2026-08-24T00:54:52.632000Z` |
| largest gap for any single provider | 32.1 s |

## Response classes observed

| class | count |
|---|---:|
| `http_429` | 1,016 |
| `http_500` | 455 |
| `http_503` | 512 |
| `http_504` | 453 |
| `ok_or_schema_miss` | 29,964 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
