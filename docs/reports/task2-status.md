# Task 2 (`surface:5`) — worker status report

**To:** orchestrator (`surface:3`). **From:** Task 2. **At:** 2026-08-23T19:04Z,
clock read with `date -u`, not assumed.

Written as a file because I cannot identify which peer session is `surface:3`
without enumerating, and a guessed message is worse than a durable report. I do
not edit `docs/ORCHESTRATION.md` — that is yours.

## Correct the board

It currently says Task 2 is not started, with no brief. That has been false for
roughly three hours. The accurate row:

| Field | Value |
|---|---|
| Brief | `docs/briefs/task2.md`, present |
| Eval design | **frozen and committed** — `9fd6ff8`, 2026-08-23T19:00:14Z |
| Amendment | `dbca310` — dating correction + meetily engine config |
| Tests | 44 passing, ruff clean |
| Engine runs | **none.** Nothing downloaded, cut, or sent to any vendor |
| Blocking on you | corpus selection (below) |

## What exists

`task2-stt-benchmark/`, all committed before any engine output existed anywhere
in the tree — which is the property that makes the numbers worth anything:

* `PREREGISTRATION.md` — primary metric **IT-term F1**; guardrail **WER ≤ 0.30**;
  tie-break order (code-switch WER → Latin→Cyrillic rate → hallucination rate →
  measured cost → latency); paired bootstrap, 10 000 resamples, seed 20260823,
  pairing enforced; separate default and tuned rankings; falsification
  conditions; amendment log.
* `docs/reference-policy.md` — 12 annotation rules, each with a worked pass and
  a worked fail.
* `glossary.json` — 50 terms, hashed, with the pre-declared rule that a Cyrillic
  transliteration of a Latin term is not a hit.
* `harness/` — hashed segment manifest, one adapter interface, identical retry
  policy in the runner, raw-output storage before normalisation, failure
  accounting, results CSV, one exact alignment shared by all metrics.
* 44 tests. `РАКа`→RAG and `Lead House`→ClickHouse are fixtures asserted to
  score as **failures**; unmeasured metrics assert `None` rather than a
  flattering `0.0`; an empty transcript scores WER 1.0; a term said elsewhere in
  the segment earns no recall credit; per-segment speaker relabelling is not
  rewarded.

## Decision I need from you

**Which corpus to freeze** — `task2-stt-benchmark/docs/corpus-candidates.md`.

Recommendation: **Радио-Т**. Four hosts, remote-call acoustics, code-switching in
nearly every sentence, public MP3s so a grader can re-hash the same file. The
catch is real and needs your ruling: the licence is **CC BY-NC-ND 3.0** and the
licence page explicitly forbids edits of the audio. My proposed posture is to
cut and analyse locally, publish metrics, short quoted error spans and the
recipe (episode, SHA-256, cut points), and **never** publish the segments or the
full reference transcript. Fallback if you read ND as blocking even local
segmentation: a CC BY conference talk with Q&A — clean rights, weaker test.

Rejected and recorded: Common Voice Russian. CC0, and useless here — read
speech, no code-switching. Clean rights did not buy a relevant corpus.

## Blockers, all local and free

| Requirement | State |
|---|---|
| `ffmpeg` / `ffprobe` | **absent** — hard blocker for the manifest |
| local ASR runtime | absent |
| RAM | 8 GB arm64 — large-v3 needs a quantised whisper.cpp build |

None needs an account or a payment. Modal is available with free credits if CPU
inference becomes the critical path; if used it will be one app named for this
benchmark with every command scoped to it, and the workspace never enumerated.

## Corrections you should propagate

1. **Parakeet is not English-only.** That was true of `parakeet-tdt-0.6b-v2`;
   `v3` covers 25 languages including Russian. With Whisper large-v3 that gives
   two self-hosted engines needing no account, so the benchmark has a floor of
   two under any account failure, and ≥5 is reachable with free tiers on top.
2. **From `Zackriya-Solutions/meetily` I took the engine configuration only** —
   quantised whisper.cpp large-v3, Parakeet v3 int8 via ONNX. I refused its
   RNNoise / EBU R128 / Silero VAD preprocessing: feeding the local engines
   cleaned audio the cloud engines never receive would make any local win an
   artefact. Proposed instead as a labelled side-experiment that measures the
   preprocessing effect without touching the ranking. Reasoning:
   `task2-stt-benchmark/docs/self-hosted-engines.md`.
3. **My own defect, fixed and logged.** The freeze headers carried hand-typed
   timestamps that were assumed rather than measured, and were *later* than the
   work they dated. Corrected in `dbca310`: the dating is now the commit's, and
   the change is recorded as an amendment, not applied silently.

## Not mine, but it fails your gate

`tests/test_monitor.py` has **3 failures** on `main` —
`KeyError: 'conditions'` at `task1-spend-observability/monitor.py:2160`. The
`AGENTS.md` pre-delivery gate (`pytest tests/ -q && ruff check .`) cannot pass
until `surface:2` fixes it. My own three files are green.
