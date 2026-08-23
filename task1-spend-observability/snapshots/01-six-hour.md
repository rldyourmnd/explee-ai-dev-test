# Window snapshot 01 — six-hour

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
| snapshot | **01** in the six-hourly sequence |
| taken at | `2026-08-23T22:13:41Z` |
| label | `six-hour` |
| repository | `f9b1728` |
| collector before | `active` |
| collector after | `active` |

## The bytes

| | |
|---|---|
| sha256 of the snapshot | `2e4b0a05bb12c35882374a21a19c6f829967864f411b6c45536826ac30b189c5` |
| sha256 of the same leading bytes on the host | `2e4b0a05bb12c35882374a21a19c6f829967864f411b6c45536826ac30b189c5` |
| snapshot is a faithful prefix of the host file | **yes** |
| size | 6,391,338 bytes |
| lines | 11,520 |
| host file had already grown by | 0 bytes at verification time |

## The window


| | |
|---|---|
| first record | `2026-08-23T16:13:26.775000Z` |
| last record | `2026-08-23T22:13:14.578000Z` |
| span | **5.9966 h** (21,588 s) |
| six hours reached | **no** |
| records | 11,520 |
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
| `http_429` | 318 |
| `http_500` | 185 |
| `http_503` | 247 |
| `http_504` | 159 |
| `ok_or_schema_miss` | 9,891 |

## Providers

`anthropic`, `bounceban`, `brightdata`, `elevenlabs`, `evomi`, `findymail`, `meta_ads`, `openai`, `openrouter`, `resend`, `scrapfly`, `tremendous`, `twocaptcha`, `vastai`, `zerobounce`

## Verifying this yourself

```bash
sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first
uv run tools/snapshot_window.py --label check --dry-run
```
