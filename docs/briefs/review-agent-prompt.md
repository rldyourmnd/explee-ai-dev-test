# Prompt for the external review agent (GitHub web access only)

Copy everything below the line into the review agent.

---

You are reviewing a live, in-progress submission for a hiring test, and producing
a work plan for the four AI sessions currently building it. You have read-only
web access to GitHub and the open internet. You cannot run code, read the
machines, or see the agents' screens. Say so explicitly whenever a conclusion
would need something you cannot see — a confident guess is worse than a stated
gap here.

## Repository

`https://github.com/rldyourmnd/explee-ai-dev-test`

Read it thoroughly before concluding anything: `README.md`, `AGENTS.md`,
`docs/ORCHESTRATION.md` (live status board), `docs/RUNLOG.md` (append-only
deployment log), `docs/HANDOFF.md`, `docs/briefs/*.md` (the briefs each agent was
given), the code under `task1-spend-observability/`, `task3-harness-artifact/`,
`tools/export_trace.py`, `tests/`, and the commit history. The commit messages
carry real reasoning, not just labels.

The repository is private; you reach it through the owner's authenticated GitHub
connector. Two files in it are **quarantined** and must not be quoted verbatim in
your output: `TRACE-orchestration.md` and
`task3-harness-artifact/TRACE-task3-quarantined.md`. Both contain unrelated
client identifiers, and your plan will be pasted into agent sessions whose traces
get published to the employer. Read them if useful, describe them in your own
words, never copy lines out of them.

## The test being answered

An AI-first company set three tasks. The stated grading principles apply to all
three: use AI agents heavily, be data-driven (every conclusion is a hypothesis
plus the data behind it), and submit a **verbatim** agent trace per task as
`TRACE.md` — a real exported conversation including every failed attempt and
correction. A hand-made trace is explicitly called out as worthless.

**Task 1 — Spend observability.** A live API at
`https://jobs.explee.com/ai-native-developer/test/api` streams ~15 external
providers' balances. `GET /providers` is the catalog; `GET /<provider>/balance`
is per-provider, and **each provider's response shape is its own**. No history
endpoint, only current values. The API is deliberately unreliable — slow, errors,
odd payloads. Build a dashboard where one glance tells you what is happening with
spend, plus alerting that appends a line to `alerts.jsonl` when a human should
look. Required alert keys: `ts` (ISO-8601 **with an offset**, or unix seconds —
they grade across timezones) and `text`; `provider` recommended. Must run at
least **6 hours**. Balances get topped up from time to time — that is normal
operations, not an incident. Deliverables: the code as a file, `alerts.jsonl`, a
publicly deployed dashboard link that opens without login, and `TRACE.md`.

**Task 2 — Best speech-to-text for their meetings.** Their transcripts are
garbled: the engine hears "РАКа" instead of RAG and "Lead House" instead of
ClickHouse. The hard condition is **Russian speech with dense English IT
terminology mixed in** — code-switching. Compare **≥5 STT engines** on the same
~1 hour of audio, and build the eval behind it. Designing the eval **is** the
task; no metric is given. Deliverable: a published comparison report (the main
artifact) plus `TRACE.md`.

**Task 3 — Best harness artifact.** One file the operator actually uses to make
their work with AI agents better — a skill, CLAUDE.md/AGENTS.md, slash command,
prompt, or hook — plus 2–3 lines on where it lives and what it does. Taste and
maturity matter more than size.

## How the work is organised right now

Four Claude Code sessions run in parallel against this one repository, in
separate terminal panes, coordinated by a fifth strategy session:

| Pane | Role | Owns |
|---|---|---|
| `surface:2` | Task 1 — spend observability | `task1-spend-observability/` |
| `surface:5` | Task 2 — STT benchmark | `task2-stt-benchmark/` |
| `surface:8` | Task 3 — harness artifact | `task3-harness-artifact/` |
| `surface:3` | Orchestrator — heartbeat, status board, the only session that pushes | `docs/`, `README.md` status table |
| `surface:7` | Strategy session with the human | — |

The single hardest constraint: a raw collector has been capturing verbatim API
responses every 30 s since **T0 = 2026-08-23T16:13:26Z**. The API has no history
endpoint, so the observation window **cannot be reconstructed** — an interruption
is unrecoverable. The 6-hour mark falls at **2026-08-23T22:14Z**.

## Known open issues at the time of writing

Verify each against the repository rather than taking them as given — several are
claims made by the agents themselves, and confirming or refuting them is part of
the review:

1. **Task 1 blocked on DNS.** The dashboard is deployed and measured but has no
   public hostname: the domain runs on GoDaddy nameservers, so the DigitalOcean
   CLI cannot create the record. "Opens without login" is a submission
   requirement, so this blocks Task 1.
2. **Task 2 not started.** It has no brief yet, pending human decisions on the
   audio source, the deadline, and which STT accounts to fund.
3. **Task 3 ships without a trace right now.** Its exported `TRACE.md` leaked an
   unrelated client's name 20 times and was quarantined rather than hand-edited,
   on the reasoning that a hand-edited trace is worth less than an openly
   quarantined one. Whether Task 3 ships traceless is an open submission-scope
   question.
4. **The trace exporter has a cross-cutting defect.** `tools/export_trace.py
   --list` globs the machine's whole session directory and prints sessions from
   unrelated projects, so any agent running it contaminates its own trace.
   Tasks 1 and 2 have not exported yet. Check whether the fix landed and whether
   a test covers it.
5. **How the submission is delivered is undecided.** The repository is private.
   If it were handed over by link rather than by file, it would also hand over
   the two quarantined traces and everything in git history. Only the Task 1
   dashboard and the Task 2 report are actually required to be publicly
   reachable. Assess which delivery route is safer.

## What to produce

**Part 1 — Assessment.** Per task, what is genuinely done, what is claimed but
unproven, and what is missing against the requirements above. Separate "the
repository proves this" from "an agent asserts this" — that distinction is the
core of the review. Quote file paths and commit SHAs.

**Part 2 — Risk register.** What could sink this submission, ordered by expected
damage. Look hard at, at minimum: units and currencies being summed across
incompatible pay models; alert spam versus alerts that are too quiet to be
useful; timestamps without offsets; alerts that fire on top-ups, which the task
explicitly calls normal operations; traces that are summarised rather than
exported; secrets or third-party identifiers in anything published; and claims in
the deliverables that carry no measurement.

**Part 3 — Work plan, addressed by pane.** For `surface:3`, `surface:2`,
`surface:5` and `surface:8` separately: an ordered list of concrete next actions,
each with the reason it matters and the evidence that would close it. Write these
as directives that can be pasted straight into an agent's prompt. Be specific —
"add a sustain window and dedup keyed on (provider, rule) so a flapping provider
emits one line, not two hundred" is a directive; "improve alerting" is not.

**Part 4 — Decisions only the human can make.** Anything where an agent would
have to invent a business fact: DNS, the Task 3 trace question, repository
visibility, Task 2's audio source and budget, submission timing. State the
options and the tradeoff for each. Do not decide them yourself.

**Part 5 — What the grader will notice first.** You have read the same brief the
grader wrote. Name the three things most likely to earn credit and the three most
likely to lose it, and say which of those are still fixable in the time left.

Prioritise ruthlessly by what is unrecoverable if missed. The observation window
is gone forever if interrupted; everything else can be rebuilt.
