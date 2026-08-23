# Orchestration status board

Four sessions run in parallel against this one repository. This file is the
single place that says what is true right now, with the measurement behind each
claim. Maintained by the orchestrator (`surface:3`); workers report, they do not
edit this file.

**Last heartbeat: 2026-08-23T17:40Z.**

## ESCALATIONS — open, for the human

Escalation channel is `cmux notify` plus this section plus the orchestrator's own
pane. **`surface:7` is not written to by this session under any circumstance** —
the owner reserves it, which supersedes the escalation instruction in
`docs/briefs/orchestrator.md`.

| # | Item | Owner's call because |
|---|---|---|
| 1 | **Repository visibility.** See below — flagged, not acted on. | Publishing decision |
| 2 | **Task 3 ships with no trace?** Its trace is quarantined; the submission requires one per task. | Submission scope |
| 3 | **Task 2 has no brief.** `surface:5` idle since 16:48Z; STT scope undecided. | Business scope |
| 4 | **Task 1 DNS.** `spend.nddev.it.com` needs an A record; GoDaddy zone, no token, rule 2 forbids pasting one. | Access the agents do not have |
| 5 | **`docs/briefs/review-agent-prompt.md` is untracked.** Owner-authored draft; not committed or pushed by this session. Say the word and it goes up. | It is the owner's draft |
| 6 | **Pre-existing pyright error**, `tools/export_trace.py:205` from `e7af3a4` — `ROLE_LABEL.get` returns `str \| None`, then `+=`. Outside every current diff; does not affect `pytest` or `ruff`. Flagged by Task 3, not fixed. | Whether a green-gates repo should also be pyright-clean |

### Repository is PRIVATE — and both directions cost something

`rldyourmnd/explee-ai-dev-test` is private. Two consequences that pull opposite
ways, so this cannot be resolved by default:

- **Left private:** a review agent with web-only GitHub access cannot read the
  repository at all, so the submission is unreadable to that reviewer.
- **Made public:** it publishes `TRACE-orchestration.md` and
  `task3-harness-artifact/TRACE-task3-quarantined.md` **including their leaks** —
  9 third-party IPs, 16 SSH `HostName` lines, unrelated client names (RUNLOG
  16:27Z), and `unrelated-client-a` ×20. It also publishes **all git history**, where
  commit `f9ef23b` still carries the Task 3 trace under its original name.
  Quarantining changed the file's disposition; it did not remove it from history.

Flagging only. This session takes no action on visibility.

## Rule 1 — raw collector (outranks everything)

`explee-raw-sampler.service` on `server-nddev-amsterdam`. The API has no history
endpoint, so an interruption is unrecoverable and cannot be faked.

| | |
|---|---|
| State | `active` |
| T0 | `2026-08-23T16:13:26.775Z` (first record, matches the logged T0) |
| Last record | `2026-08-23T17:39:31.410Z`, 27 s before the check |
| Lines | 2768 (+480 since 17:24Z) |
| Growth | 31.8 lines/min over 15.1 min — matches the expected ~32 |
| Gaps > 45 s | **0**, verified across every consecutive record pair |
| Malformed lines | 0 |
| Elapsed | 1 h 26 m of the 6 h minimum |
| 6 h mark | `2026-08-23T22:14Z` — **4 h 34 m remaining** |

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

**Unblocked and working.** The owner closed the DNS menu at ~17:30Z; the agent is
back on "deploy dashboard publicly" as of 17:40Z, 12 min into the step.

Committed `79be7bd` since the last heartbeat — stops a reverted balance blip
being read as phantom spend, reasoned against a provider burning 0.28 USD/h.
That is the kind of correction that only comes from looking at real captured
data, which is what the 6 h window is for.

DNS itself is still unresolved as a public-hostname question; it remains
escalation #4 until a URL answers in incognito.

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

**Artifact done and clean. Trace quarantined — one open question for the human:
Task 3 now ships with no trace.**

Resolved at 17:25Z in `2eeaefc`: the trace was renamed to
`TRACE-task3-quarantined.md` and a `QUARANTINE.md` records the disposition,
matching how `TRACE-orchestration.md` was handled. No hand-edit, no history
rewrite — the route I asked for. Rescanned at 17:25Z: `README.md` and
`reviewer-protocol.md` are clean on every pattern; the leak is confined to the
quarantined file, which is no longer a submission artifact.

**Open question, human's to answer:** the submission requires every `TRACE.md`
to be exported via `tools/export_trace.py`, and Task 3 no longer has one. The
agent is weighing a re-run to produce a clean trace and has stated it would
rather submit no trace than a staged one. That is a submission-scope judgement,
not a technical one. Escalated 17:25Z.

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

## Open cross-cutting risk: `tools/export_trace.py --list` leaks every project

The Task 3 leak was not a Task 3 mistake. It came from the shared exporter, so
**Tasks 1 and 2 will reproduce it identically** unless they are warned before
they export. Root cause, verified in the source rather than taken on report:

- `tools/export_trace.py:30` — `PROJECTS = ~/.claude/projects`
- `:247` — `--list` walks every project directory on the machine, so the tool
  result names unrelated clients
- `:228-230` — `--max-result` truncates head-first (`body[:max_result]`), and
  the leak sits in row 1 of the result, so no value removes it without gutting
  every tool result in the trace
- `--allow-finding` / `--allow-secrets` widen the credential gate only; neither
  drops content

Consequence: **do not run `--list` in a session that will be exported.** Get the
session id another way.

`AGENTS.md`'s `grep -c HostName` gate is also unsatisfiable in principle — it
matches the bare word, so any trace that quotes the rule fails it. Matching
`HostName\s+\S+` would test SSH config content instead of the word.

**Closed at 17:40Z — fixed at the source, so the warning is now moot.**

The owner delivered the warning to `surface:2` at ~17:30Z after closing its menu
with Escape. Task 3 then fixed both defects in `d7c2b24`, and I verified the fix
by running it rather than reading the diff:

```
uv run tools/export_trace.py --list
→ 3 rows, all -Users-rldyourmnd-Developer-rldyourmnd-explee-ai-dev-test
→ 0 foreign project slugs
```

`list_sessions()` now takes a single project and scopes the error path too, so a
missing project cannot leak the names of the projects it found instead — the
failure mode one level past the obvious one.

It also **corrected my proposed regex.** I suggested `HostName\s+\S+` for the
`AGENTS.md` gate; Task 3 pointed out that is still self-matching, because in
`grep -c HostName TRACE.md` the filename is the non-space token. The gate is now
anchored to line start (`^[[:space:]]*HostName[[:space:]]+`), which tests what an
SSH config block actually looks like. The better fix came from the agent that
owned the file.

**No warning sent to `surface:5`.** It is at a clean prompt, but the defect it
warned about no longer exists, and typing into it would open its session ahead of
the owner's brief. Stale advice delivered early is worse than no advice.

## Deadlines

| When | What | Standing |
|---|---|---|
| 2026-08-23T22:14Z | 6 h observation minimum; longer is better | on track, 0 gaps |
| before submission | every `TRACE.md` exported via `tools/export_trace.py`, never hand-written | not yet due |
| before submission | dashboard and report open in incognito, no login | not yet due |
| before submission | `uv run --with pytest pytest tests/ -q && ruff check .` green | **green at 17:32Z** — 84 passed in 2.24 s, `ruff` all checks passed, both exit 0 |

## Push state

**Synced at 17:41Z, `origin/main` = `79be7bd`, 0 commits ahead.** Gates run
before each push, never after:

| Time | Gate result | Pushed |
|---|---|---|
| 17:32Z | 84 passed, ruff clean, both exit 0 | `f086fe9..9c11385`, 7 commits |
| 17:41Z | **93 passed**, ruff clean, both exit 0 | `ae2c7cb..79be7bd`, 2 commits |

The test count rose 84 → 93 because Task 3 shipped tests with its exporter fix
rather than asserting it worked.

Not committed: `.serena/` tooling churn, and `docs/briefs/review-agent-prompt.md`
— an untracked draft the owner authored in a directory this session owns. Left
alone deliberately: committing someone's open draft captures whatever half-state
it happens to be in, and pushing it publishes it. Flagged as escalation #5.

The push includes commit `f9ef23b`, which carries the Task 3 trace under its
original name with the leak intact. That is acceptable **only while the
repository stays private** — see the visibility escalation above.

## Working-tree discipline

Each agent commits only its own directory; the orchestrator owns `docs/` and the
`README.md` status table and is the only session that pushes to `origin`, and
only on green `pytest` and `ruff`. A `.git/index.lock` means another agent is
mid-commit — wait and retry, never delete it.

At 17:25Z the only uncommitted work is `.serena/` (tooling cache, ignored by
agreement) and `docs/RUNLOG.md`.

**One coordination issue, not a correctness one:** Task 1 wrote its 17:10Z
deploy entry into `docs/RUNLOG.md`, which this session owns, and left it
uncommitted. The entry itself is accurate and belongs there — RUNLOG is the
shared deploy record — so it was committed as written rather than rewritten. The
risk is that an uncommitted file in a directory another session also edits can
be clobbered by whoever saves next. Task 1 will be asked to commit RUNLOG
entries promptly, at the same time as the `--list` warning.

## Heartbeat log

| Time | Collector | Observed |
|---|---|---|
| 16:48Z | `active`, 1104 lines, 0 gaps | T1 characterizing data; T3 reading local config; T2 unbriefed and idle → escalated to human |
| 17:02Z | `active`, 1520 lines, +31.5/min, 0 gaps | T1 building `monitor.py`, iterating on diagnostics; T3 artifact written but idle, untracked, no trace → nudged, leak scan clean; T2 unchanged, still awaiting human |
| 17:14Z | `active`, 1904 lines, +31.9/min, 0 gaps | T1 monitor deployed and measured, now **blocked on DNS** → escalated; T3 committed `f9ef23b` but its `TRACE.md` carries a **rule-3 leak** (unrelated client ×20) → returned to owner, escalated; T2 unchanged |
| 17:25Z | `active`, 2288 lines, +32.1/min, 0 gaps | T3 quarantined the trace cleanly (`2eeaefc`) and root-caused it to the shared exporter — Tasks 1 and 2 are exposed to the same defect; T1 still holding the DNS menu, unchanged; T2 unchanged |
| 17:40Z | `active`, 2768 lines, +31.8/min, 0 gaps | T1 unblocked, deploying dashboard, committed `79be7bd`; T3 fixed both exporter defects in `d7c2b24`, verified by running `--list` (0 foreign slugs) — cross-cutting risk **closed**; gates green at 93 passed, pushed to `origin/main`; T2 unchanged |
