# Window snapshot 06 - twenty-four-hour

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
| snapshot | **06** in the six-hourly sequence |
| taken at | `2026-08-24T16:22:52Z` |
| label | `twenty-four-hour` |
| repository | `027b1b8` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `31b592684b3dcea72d176d9b632a1c425930f457f1fe920280562d202980970e` |
| sha256 of the same leading bytes on the host | `31b592684b3dcea72d176d9b632a1c425930f457f1fe920280562d202980970e` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 25,537,870 bytes |
| lines | 46,352 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-24T16:22:37.685000Z` |
| span | **24.1530 h** (86,951 s) |
| six hours reached | **yes** |
| records | 46,352 |
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
| `http_429` | 1,359 |
| `http_500` | 638 |
| `http_503` | 742 |
| `http_504` | 612 |
| `ok_or_schema_miss` | 40,104 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
