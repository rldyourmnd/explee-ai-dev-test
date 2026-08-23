# Orchestration status board

Four sessions run in parallel against this one repository. This file is the
single place that says what is true right now, with the measurement behind each
claim. Maintained by the orchestrator (`surface:3`); workers report, they do not
edit this file.

**Last heartbeat: 2026-08-23T17:02Z.**

## Rule 1 — raw collector (outranks everything)

`explee-raw-sampler.service` on `server-nddev-amsterdam`. The API has no history
endpoint, so an interruption is unrecoverable and cannot be faked.

| | |
|---|---|
| State | `active` |
| T0 | `2026-08-23T16:13:26.775Z` (first record, matches the logged T0) |
| Last record | `2026-08-23T17:00:29.460Z`, 23 s before the check |
| Lines | 1520 (+416 since 16:47Z) |
| Growth | 31.5 lines/min over 13.2 min — matches the expected ~32 |
| Gaps > 45 s | **0**, verified across every consecutive record pair |
| Malformed lines | 0 |
| Elapsed | 0 h 47 m of the 6 h minimum |
| 6 h mark | `2026-08-23T22:14Z` — **5 h 14 m remaining** |

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

- Done: raw capture live since T0; raw-data characterization complete (its own
  task list shows that item completed at 17:02Z).
- In flight: `monitor.py` — replay + tail + SQLite WAL + alerting. Untracked
  `task1-spend-observability/monitor.py` exists on disk; the agent is running it
  end to end (`--once` replay against `raw_samples.jsonl`, then re-parsing the
  emitted `alerts.jsonl`) and iterating on 5 diagnostics in that file.
- Pending (its own plan): tests + ruff clean, public dashboard over HTTPS with
  no login, reach the 6 h window and export `TRACE.md`.
- Evidence: read from `surface:2` at 17:02Z.

### Task 2 — STT benchmark (`surface:5`, `task2-stt-benchmark/`)

**Blocked — not started, no brief.** Unchanged at 17:02Z: session still at the
Claude Code welcome screen with an empty prompt, no `docs/briefs/task2.md`, and
no `task2-stt-benchmark/` directory. Escalated once at 16:48Z; not re-notified,
because repeating an unanswered escalation every 12 minutes trains the human to
ignore the channel.

This is a human decision, not one the orchestrator answers: the benchmark's
scope (which STT providers, which audio, which metrics, where the report is
published) determines the deliverable. Escalated to `surface:7` at 16:48Z.

Cost of the delay is bounded — unlike Task 1, nothing here decays with wall
time, so this does not threaten the 22:14Z window. It does consume the shortest
path to a published report.

### Task 3 — harness artifact (`surface:8`, `task3-harness-artifact/`)

**Artifact written, not yet finalized.** Agent went idle at an empty prompt at
~17:02Z having produced its deliverable but without committing or exporting a
trace — the "idle after finishing" failure mode. Nudged on those two specific
gaps at 17:02Z.

- Done: `task3-harness-artifact/README.md` (599 B) and `reviewer-protocol.md`
  (10.2 KB) on disk. The artifact is the contract loaded by a `/ry-review` wave:
  how six read-only reviewer subagents run in parallel, what a finding must
  carry (severity, confidence, location, evidence, impact, fix, disposition),
  and a file-first output transport — full report to disk, ≤4 KB summary back to
  the parent — so a review wave cannot overflow the orchestrator's context.
  Its README states the tradeoff it made rather than hiding it: as a
  `references/` file it carries no frontmatter trigger, accepted in exchange for
  self-containment, which the brief makes a hard constraint.
- Outstanding: directory is untracked, and no `TRACE.md` exists.
- **Confidentiality check passed.** This task reads local machine configuration,
  the exact shape that contaminated the orchestration trace (RUNLOG 16:27Z: 9
  third-party IPs, 16 SSH `HostName` lines, unrelated client names). Scanned
  both files at 17:02Z for IPs, `HostName`, `nddev`/`unrelated-client-b`/`unrelated-client-a`,
  local user paths, and credential patterns: **clean**. The only hits were the
  words "security", "secrets" and "tokens" used topically. Reading env key names
  rather than values is what kept it clean; the export still has to hold that
  line, because traces publish verbatim.
- Evidence: read from `surface:8` at 17:02Z; `ls` and `grep` over the artifact.

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

Untracked at 17:02Z: `.serena/` (tooling cache),
`task1-spend-observability/monitor.py` (Task 1, in flight) and
`task3-harness-artifact/` (Task 3, awaiting its own commit). No scope bleed
observed — every worker's writes are inside its own directory.

## Heartbeat log

| Time | Collector | Observed |
|---|---|---|
| 16:48Z | `active`, 1104 lines, 0 gaps | T1 characterizing data; T3 reading local config; T2 unbriefed and idle → escalated to human |
| 17:02Z | `active`, 1520 lines, +31.5/min, 0 gaps | T1 building `monitor.py`, iterating on diagnostics; T3 artifact written but idle, untracked, no trace → nudged, leak scan clean; T2 unchanged, still awaiting human |
