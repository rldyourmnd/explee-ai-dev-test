# Prompt for the external review agent — round 2

**Status: COMPLETE — historical.** The round-2 external-review prompt as issued. Its review, and its unresolved gap, are in `docs/reviews/`.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


Copy everything below the line.

---

You are running the **second** review round on an in-progress hiring-test
submission, and producing an updated work plan for the four AI sessions building
it. You have authenticated read-only access to GitHub through the owner's
connector, plus public web access. You cannot run code, reach the machines, or
see the agents' screens — so say so explicitly whenever a conclusion would need
something you cannot see. A confident guess is worse than a stated gap here.

## Repository

`https://github.com/rldyourmnd/explee-ai-dev-test` — review current `main`.

**Read your own previous review first:**
`docs/reviews/external-review-2026-08-23T18-05Z.md`. It was committed into the
repository and dispatched to the four sessions as work orders, so much of what
you find will be a response to it. Your first job is to judge those responses.

Then read `README.md`, `AGENTS.md`, `docs/ORCHESTRATION.md` (status board),
`docs/RUNLOG.md`, `docs/briefs/*.md` (including `orchestrator-mandate.md`, which
expanded the orchestrator's authority), `docs/reports/*`, the code under
`task1-spend-observability/`, `task2-stt-benchmark/`, `task3-harness-artifact/`,
`tools/export_trace.py`, `tests/`, and the commit history since `6efe631`. The
commit messages carry real reasoning — several are retractions, and those are the
most informative objects in the repository.

Two files are **quarantined** and must not be quoted verbatim in your output:
`TRACE-orchestration.md` and any file named `TRACE-*-quarantined.md`. They contain
unrelated client identifiers, and your plan gets pasted into agent sessions whose
traces are published to the employer. Read them if useful; describe them in your
own words; never copy lines out.

## The test being answered

An AI-first company set three tasks. The stated grading principles apply to all
three: use AI agents heavily, be data-driven (every conclusion is a hypothesis
plus the data behind it), and submit a **verbatim** agent trace per task as
`TRACE.md` — a real exported conversation including every failed attempt and
correction. A hand-made trace is explicitly called worthless.

**Task 1 — Spend observability.** A live API at
`https://jobs.explee.com/ai-native-developer/test/api` streams ~15 providers'
balances; `GET /providers` is the catalog, `GET /<provider>/balance` is
per-provider, and each response shape is its own. No history endpoint. The API is
deliberately unreliable. Build a dashboard where one glance tells you what is
happening with spend, plus alerting that appends to `alerts.jsonl` when a human
should look. Required alert keys: `ts` (ISO-8601 with an offset, or unix seconds)
and `text`; `provider` recommended. Must run **at least 6 hours**. Top-ups are
normal operations, not incidents. Deliverables: code as a file, `alerts.jsonl`, a
public dashboard link that opens without login, and `TRACE.md`.

**Task 2 — Best speech-to-text for their meetings.** Their transcripts are
garbled: the engine hears "РАКа" for RAG and "Lead House" for ClickHouse. Hard
condition: Russian speech with dense English IT terminology, code-switching.
Compare **≥5 engines** on the same ~1 hour of audio and build the eval behind it.
Designing the eval **is** the task — no metric is given. Deliverable: a published
comparison report plus `TRACE.md`.

**Task 3 — Best harness artifact.** One file the operator actually uses to make
their work with AI agents better, plus 2–3 lines on where it lives and what it
does. Taste and maturity over size.

## What changed since your last review

Verify each of these against the repository rather than believing it — several
are claims by the same agents you audited:

- **The Task 1 dashboard is now public.** `spend.nddev.it.com` was created via
  the GoDaddy CLI and, verified from outside the deployment host with no `Host`
  override, no cookies and no local DNS override, returns 200 with a valid
  Let's Encrypt certificate for that exact hostname. Check it yourself over the
  public web — that is within your reach and is the single acceptance criterion
  you can independently close.
- **Task 2 started.** It has a brief, a frozen `PREREGISTRATION.md`, a
  reference-transcript policy, a hashed glossary and a harness. No engine has
  been run yet, deliberately: the design was frozen before any output existed.
  Judge whether that pre-registration is genuine or decorative — whether it
  actually constrains later choices, and whether its amendments are recorded as
  amendments rather than silent edits.
- **The orchestrator's mandate was expanded** to own outcomes, accept or reject
  worker output, and make technical decisions. Only four things now need the
  human: spending money, publishing the repository, interrupting the collector,
  and submitting.
- **A contradiction sweep ran**, retracting claims the repository's own code and
  commits disproved — including a headline `README.md` claim about HTTP 429 that
  turned out to rest on evidence gathered *before* the observation window opened.
- **Your cross-cutting exporter finding was extended**, and a third instance of
  the same class was found in a different tool. Judge whether the general lesson
  was learned or only the specific instances patched.

## What to produce

**Part 1 — Closure audit.** Go through your previous review finding by finding.
For each: closed with evidence, closed by assertion only, partially addressed,
still open, or *wrongly* closed — the last being a fix that does not do what its
commit message claims. Cite the commit or file that closes it. Be willing to say
a finding of yours was wrong; the repository contains at least one case where an
agent disproved its own headline claim, and you should hold yourself to that.

**Part 2 — New findings.** Only things not in the previous round. Look hardest at
the newest code, which has had the least scrutiny: the Task 2 harness and metric
implementations, the alerting changes made in response to you, and the CI
configuration. Separate "the repository proves this" from "an agent asserts this".

**Part 3 — Risk register, re-ranked.** What could still sink this submission,
ordered by expected damage, with what would close each. Note explicitly which
risks have moved since the last round and in which direction.

**Part 4 — Work plan by pane.** For `surface:3` (orchestrator), `surface:2`
(Task 1), `surface:5` (Task 2) and `surface:8` (Task 3) separately: an ordered
list of concrete next actions, each with why it matters and what evidence closes
it. Write them as directives that paste straight into an agent prompt. "Add a
sustain window and dedup keyed on (provider, rule) so a flapping provider emits
one line, not two hundred" is a directive; "improve alerting" is not.

**Part 5 — Submission readiness.** Is this submittable now? If not, the shortest
honest path to submittable, and the three things most likely to earn credit and
the three most likely to lose it. Distinguish what is still fixable in the time
remaining from what is already fixed or already lost.

Prioritise by what is unrecoverable if missed. The observation window is the only
thing that cannot be rebuilt.
