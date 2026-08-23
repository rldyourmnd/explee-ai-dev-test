# Orchestration status board

Four sessions run in parallel against this one repository. This file is the
single place that says what is true right now, with the measurement behind each
claim. Maintained by the orchestrator (`surface:3`); workers report, they do not
edit this file.

**Last heartbeat: 2026-08-23T17:14Z.**

## Rule 1 — raw collector (outranks everything)

`explee-raw-sampler.service` on `server-nddev-amsterdam`. The API has no history
endpoint, so an interruption is unrecoverable and cannot be faked.

| | |
|---|---|
| State | `active` |
| T0 | `2026-08-23T16:13:26.775Z` (first record, matches the logged T0) |
| Last record | `2026-08-23T17:12:30.005Z`, 25 s before the check |
| Lines | 1904 (+384 since 17:00Z) |
| Growth | 31.9 lines/min over 12.0 min — matches the expected ~32 |
| Gaps > 45 s | **0**, verified across every consecutive record pair |
| Malformed lines | 0 |
| Elapsed | 0 h 59 m of the 6 h minimum |
| 6 h mark | `2026-08-23T22:14Z` — **5 h 01 m remaining** |

Task 1 deployed its monitor against this log at 17:10Z with the data directory
mounted **read-only**, which makes rule 1 structural rather than a promise, and
confirmed `systemctl is-active` before and after. The sampler was not touched.

Gap-freeness is checked by parsing every `ts` in `raw_samples.jsonl` and
diffing consecutive pairs, not by trusting the line count — a count can grow
while a gap sits in the middle. Records carry per-request timestamps (~16 per
30 s cycle), so the max legitimate inter-record delta is well under 45 s.

No gaps have occurred. If one ever does it goes in `docs/RUNLOG.md` with exact
start and end, and to the human immediately. A recorded gap is data; a concealed
one invalidates the submission.

## Tasks

### Task 1 — spend observability (`surface:2`, `task1-spend-observability/`)

**Blocked on a human decision — DNS.** Escalated to `surface:7` at 17:14Z.

- Done: raw-data characterization; `monitor.py` built and committed (`8df4d72`,
  adapters, robust burn, alert rules); monitor deployed at 17:10Z as a container
  on the existing edge proxy.
- Measured, not asserted: replay of 1856 records in 5.3 s; `GET /` → 200,
  42145 bytes, 0.078 s; `GET /healthz` → 200, 15 providers, 14 fresh, 1 stale
  (`bounceban`, mid-outage). Verified with an explicit `Host` header because DNS
  does not exist yet.
- **Blocked:** `nddev.it.com` is served by GoDaddy nameservers, not DigitalOcean,
  so `doctl` cannot create the record (`domain get` → 404, account manages zero
  domains) and no DNS token is present. Rule 2 forbids obtaining one by pasting
  it into a prompt. This blocks the "dashboard reachable in incognito, no login"
  submission requirement.
- The agent rejected a `nip.io` wildcard shortcut on its own reasoning: it
  encodes the server address in the hostname, so the public URL would carry an IP
  into a published trace and fail the rule 3 scan by construction. Correct call.
- Pending: tests + ruff clean, reach the 6 h window, export `TRACE.md`.
- Evidence: read from `surface:2` at 17:14Z; RUNLOG 17:10Z; `git log 8df4d72`.

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

**Artifact clean, trace contaminated. Not done.** Committed as `f9ef23b` after
the 17:02Z nudge, but the exported `TRACE.md` carries a rule-3 leak.

### Rule-3 finding on `task3-harness-artifact/TRACE.md`, 17:14Z

Turn `[78]`, a "List available sessions" tool result, dumped a 20-row session
directory listing into the trace. Every row names an **unrelated client
project**:

```
2026-08-02 22:12   1410K   2f6b3453-…   unrelated-client-a
```

Full scan I ran over the file, so the numbers are checkable:

| Pattern | Count | Verdict |
|---|---|---|
| IP addresses | 0 | clean |
| `HostName` | 8 | benign — all its own scan commands quoted back, not config |
| `nddev` | 11 | in scope — this submission's own infrastructure, already public in `README.md` and `RUNLOG.md` |
| `unrelated-client-a` | **20** | **leak** |
| `/Users/rldyourmnd/…` | 25 | lower severity — local username and plugin-cache paths |

This is the RUNLOG 16:27Z pattern reproduced inside a trace that is meant to
publish. It cannot be repaired by editing: verbatim is the requirement, and a
hand-edited trace is worth less than an openly quarantined one. Route is
re-export at source excluding that tool result, or quarantine and record it —
`surface:8` was told to pick one, and told explicitly not to hand-edit the file
or rewrite history to hide that it happened.

**Why its own check passed.** The agent scanned for IPs and `HostName`, got 0,
and concluded the trace was clean. The scan was correct; the inference was not.
This leak contains neither pattern. A passing scan is evidence only for the
patterns it tests — which is the general form of the "claim without evidence"
failure mode, in its most convincing disguise: a real measurement supporting a
conclusion it does not reach.

- Done: `task3-harness-artifact/README.md` (599 B) and `reviewer-protocol.md`
  (10.2 KB) on disk. The artifact is the contract loaded by a `/ry-review` wave:
  how six read-only reviewer subagents run in parallel, what a finding must
  carry (severity, confidence, location, evidence, impact, fix, disposition),
  and a file-first output transport — full report to disk, ≤4 KB summary back to
  the parent — so a review wave cannot overflow the orchestrator's context.
  Its README states the tradeoff it made rather than hiding it: as a
  `references/` file it carries no frontmatter trigger, accepted in exchange for
  self-containment, which the brief makes a hard constraint.
- The two artifact files remain **clean** — rescanned at 17:14Z. Only the trace
  is affected, so the deliverable itself is not in question.
- Outstanding: resolve the trace (re-export or quarantine).
- Its decision to skip the advisory `serena-memory-sync` was right and was
  confirmed: it would write `.serena/memories/` into a tree three live sessions
  share, and nobody asked for it.
- Evidence: read from `surface:8` at 17:14Z; `git log f9ef23b`; pattern scan
  over `TRACE.md` reproduced in the table above.

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
| 17:14Z | `active`, 1904 lines, +31.9/min, 0 gaps | T1 monitor deployed and measured, now **blocked on DNS** → escalated; T3 committed `f9ef23b` but its `TRACE.md` carries a **rule-3 leak** (unrelated client ×20) → returned to owner, escalated; T2 unchanged |
