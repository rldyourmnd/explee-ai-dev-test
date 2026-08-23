# Orchestration status board

Four sessions run in parallel against this one repository. This file is the
single place that says what is true right now, with the measurement behind each
claim. Maintained by the orchestrator (`surface:3`); workers report, they do not
edit this file.

**Last heartbeat: 2026-08-23T16:48Z.**

## Rule 1 — raw collector (outranks everything)

`explee-raw-sampler.service` on `server-nddev-amsterdam`. The API has no history
endpoint, so an interruption is unrecoverable and cannot be faked.

| | |
|---|---|
| State | `active` |
| T0 | `2026-08-23T16:13:26.775Z` (first record, matches the logged T0) |
| Last record | `2026-08-23T16:47:29.041Z`, 12 s before the check |
| Lines | 1104 |
| Gaps > 45 s | **0**, verified across every consecutive record pair |
| Malformed lines | 0 |
| Elapsed | 0 h 34 m of the 6 h minimum |
| 6 h mark | `2026-08-23T22:14Z` — **5 h 27 m remaining** |

Gap-freeness is checked by parsing every `ts` in `raw_samples.jsonl` and
diffing consecutive pairs, not by trusting the line count — a count can grow
while a gap sits in the middle. Records carry per-request timestamps (~16 per
30 s cycle), so the max legitimate inter-record delta is well under 45 s.

No gaps have occurred. If one ever does it goes in `docs/RUNLOG.md` with exact
start and end, and to the human immediately. A recorded gap is data; a concealed
one invalidates the submission.

## Tasks

### Task 1 — spend observability (`surface:2`, `task1-spend-observability/`)

**In flight.** Working, not blocked.

- Done: raw capture live since T0; local `data/raw_samples.jsonl` under analysis.
- In flight: characterizing raw data — schemas, error modes, burn rate, top-ups.
  Screen shows it building a per-provider `extract()` over the catalog response.
- Pending (its own plan): `monitor.py` (replay + tail + SQLite WAL + alerting),
  tests + ruff, public dashboard over HTTPS with no login, trace export.
- Evidence: read from `surface:2` at 16:48Z; task list visible with item 1 in
  progress, 5 pending.

### Task 2 — STT benchmark (`surface:5`, `task2-stt-benchmark/`)

**Blocked — not started, no brief.** Session is at the Claude Code welcome
screen with an empty prompt; there is no `docs/briefs/task2.md` on disk, only
`task1.md` and `task3.md`.

This is a human decision, not one the orchestrator answers: the benchmark's
scope (which STT providers, which audio, which metrics, where the report is
published) determines the deliverable. Escalated to `surface:7` at 16:48Z.

Cost of the delay is bounded — unlike Task 1, nothing here decays with wall
time, so this does not threaten the 22:14Z window. It does consume the shortest
path to a published report.

### Task 3 — harness artifact (`surface:8`, `task3-harness-artifact/`)

**In flight.** Working, not blocked.

- In flight: inspecting local Claude Code configuration — reading `settings.json`
  for env **key names only** and the enabled-plugin list.
- Note for the trace: this task reads local machine configuration, which is the
  exact shape that contaminated the orchestration trace (see RUNLOG 16:27Z).
  `AGENTS.md` rules 2 and 3 apply. Watching its export for host names, IPs and
  unrelated project names; a published trace is verbatim and cannot be fixed
  afterwards. Reading key names rather than values is the right instinct.
- Evidence: read from `surface:8` at 16:48Z.

## Deadlines

| When | What | Standing |
|---|---|---|
| 2026-08-23T22:14Z | 6 h observation minimum; longer is better | on track, 0 gaps |
| before submission | every `TRACE.md` exported via `tools/export_trace.py`, never hand-written | not yet due |
| before submission | dashboard and report open in incognito, no login | not yet due |
| before submission | `uv run --with pytest pytest tests/ -q && ruff check .` green | not yet due |

## Working-tree discipline

Each agent commits only its own directory; the orchestrator owns `docs/` and the
`README.md` status table and is the only session that pushes to `origin`, and
only on green `pytest` and `ruff`. A `.git/index.lock` means another agent is
mid-commit — wait and retry, never delete it.

Untracked at 16:48Z: `.serena/` (tooling cache) and `docs/briefs/`. No worker
has touched another task's directory.

## Heartbeat log

| Time | Collector | Observed |
|---|---|---|
| 16:48Z | `active`, 1104 lines, 0 gaps | T1 characterizing data; T3 reading local config; T2 unbriefed and idle → escalated to human |
