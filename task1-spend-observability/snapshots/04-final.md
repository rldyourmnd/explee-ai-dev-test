# Window snapshot 04 - final

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
| snapshot | **04** in the six-hourly sequence |
| taken at | `2026-08-23T23:41:18Z` |
| label | `final` |
| repository | `5553aec` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `d2c0b09182c25c7fdffa12ffad7fc463b949306792276a0aa3c1cce3a969309f` |
| sha256 of the same leading bytes on the host | `d2c0b09182c25c7fdffa12ffad7fc463b949306792276a0aa3c1cce3a969309f` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 7,941,618 bytes |
| lines | 14,320 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-23T23:40:48.933000Z` |
| span | **7.4562 h** (26,842 s) |
| six hours reached | **yes** |
| records | 14,320 |
| malformed records | **0** |
| providers seen | 15 |

## Continuity

A gap is the only thing that could invalidate a window that cannot be
recreated, so it is measured rather than asserted.

| | |
|---|---|
| largest gap between cycles | **29.7 s** |
| at | `2026-08-23T23:32:48.517000Z` |
| largest gap for any single provider | 32.0 s |

## Response classes observed

| class | count |
|---|---:|
| `http_429` | 404 |
| `http_500` | 203 |
| `http_503` | 274 |
| `http_504` | 197 |
| `ok_or_schema_miss` | 12,347 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
