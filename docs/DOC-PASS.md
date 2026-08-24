# Documentation pass — run after every worker reports done

**Status: COMPLETE — historical.** The brief for the documentation pass. The pass has been run; this is the standard it was held to.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


Starts only when code has stopped moving. Documenting a moving target produces
documents that are wrong by the time they are committed, which is the failure
this repository has hit repeatedly: a stale board, a README recommending a
withdrawn engine, an acceptance matrix behind its own HEAD.

## The one rule

**Every document is either current, or explicitly historical.** There is no third
state, and "was true when written" is not a defence — a reader cannot tell.

A document that describes a plan we have since executed does not get deleted. The
plan and its execution are the evidence of how the work was done, and this
submission is graded on exactly that. It gets a status line at the top saying
what it was and that it is complete, so nobody mistakes it for an instruction.

## Inventory and treatment

### Read first by a grader — must be current, no exceptions

| File | Check |
|---|---|
| `README.md` | Every claim verifiable in one step. No recommendation the report has withdrawn. No "every task ships a trace" unless all three do. Links to `ALERT-AUDIT.md`, the snapshot series, and both live URLs. Opens with the collector-first sentence: we started the immutable collector before designing the monitor because the API has no history endpoint. |
| `AGENTS.md` | Rules match what the code and tooling actually enforce. Every gate it names must be runnable and passable. It has already carried one unsatisfiable gate; grep every command in it and run them. |
| `task1-spend-observability/README.md` | Describes the shipped `monitor.py`, the snapshot series, the clean window and T1, and points at the audit. |
| `task2-stt-benchmark/README.md` | Corpus, engines, tracks and recommendation match the published report exactly. This file said "not started" hours after publication; do not let it drift again. |
| `task3-harness-artifact/README.md` | Two to three lines, as the task requires. Location, what loads it, the honest tradeoff. Nothing more. |

### Working record — historical by nature, must be honest

| File | Treatment |
|---|---|
| `docs/RUNLOG.md` | Append-only. Never rewrite an entry. Add the closing entries: T1 declaration with its SHA, each snapshot in the series, the clean-window regeneration. |
| `docs/ORCHESTRATION.md` | Final heartbeat states the end state and stops. Add a line saying the board is closed and which document supersedes it. |
| `docs/ACCEPTANCE.md` | The one document that must be exactly true at the final SHA. Every row: verification command, its output, the SHA it ran at. No row marked done on an agent's word. |
| `docs/reviews/` | Three external reviews plus the methodology ruling. The round-2 gap is recorded rather than papered over; keep it that way. |

### Plans that became history — status line, then leave them alone

`docs/FINAL-PLAN.md`, `docs/SUBMISSION.md`, `docs/ui-spec.md`, `docs/modal-guide.md`,
`docs/briefs/*.md`.

Each gets a one-line header: what it was for, when it was written, and whether it
is complete. They are the record of how the work was directed, and a grader
reading `docs/briefs/` learns more about how this was built than from any summary
we could write afterwards. Do not tidy them into hindsight.

`docs/TASK.md` stays verbatim. It is the authority and must never be edited.

### Instruction files

`AGENTS.md` is the single source of working rules. `.claude/CLAUDE.md` correctly
refuses to restate them and carries only Claude Code specifics. **Preserve that
split.** If a rule needs changing, change it in `AGENTS.md` only.

Check both against reality: `tools/cmux_send.sh` exists and is the mandated path,
the four gates run and pass, the pinned versions in `CLAUDE.md` match
`.github/workflows/ci.yml`. A pinned version that disagrees with CI is a lie about
what was tested.

### Serena memories

`.serena/` is gitignored and does not ship. Populating it serves future work on
this repository, not the submission. Low priority, and only if everything above
is done: a short factual record of architecture, the collector rule, the alerting
model and the Task 2 evaluation design. Facts only, no plans, no chat history.

## Sweep for the defect classes this project actually produced

Not a generic checklist. These are the mistakes that happened here, so check for
them by name:

1. **A claim the code beside it disproves.** `monitor.py` once said credits are
   never summed on a line near where it summed them.
2. **A gate that cannot pass.** `grep -c HostName` matched the word in the rule
   quoting itself.
3. **A check that passes while testing the wrong thing.** A snapshot check that
   looked in the wrong directory; a scan that proved absence of IPs and was read
   as proving absence of leaks.
4. **A status that outlived its evidence.** Boards and matrices behind HEAD.
5. **A timestamp from the future**, or one hand-typed rather than measured.
6. **An identifier that should never have been typed.** Third-party project names
   belong in a gitignored pattern file, never in a tracked document — including
   inside a command that searches for them.
7. **A number without its basis.** Every figure carries units and what it is
   relative to.
8. **An em dash.** Zero on both public pages; keep it that way in the repository
   documents a grader will read.

## Definition of done

`uv run tools/repo_checks.py consistency` passes, all four gates green at a clean
tree, every document in the first table verified claim by claim against the code,
every plan document carrying its status line, and `docs/ACCEPTANCE.md` true at the
exact final SHA.
