# Prompt for the external review agent — round 3

Copy everything below the line.

---

You are running the **third** review round on a hiring-test submission that is
approaching delivery. Rounds one and two hunted defects; this round decides
whether the work is submittable, and if not, what the shortest honest path is.
You have authenticated read-only access to GitHub through the owner's connector,
plus public web access. You cannot run code, reach the machines, or see the
agents' screens — say so explicitly wherever a conclusion would need something
you cannot observe.

## Repository

`https://github.com/rldyourmnd/explee-ai-dev-test` — review current `main`.

Read, in this order:

1. `docs/TASK.md` — the **verbatim** task text, the authority for every
   acceptance decision. Where any of our documents paraphrase it, the paraphrase
   is wrong. Grade against this file, not against our summaries.
2. `docs/reviews/` — your own two previous reviews. Round three's first job is
   judging what happened to round two's findings.
3. `docs/ACCEPTANCE.md` — the acceptance matrix, and `docs/ORCHESTRATION.md` —
   the live status board. Both have been stale before; check them against the
   tree rather than believing them.
4. The deliverables: `task1-spend-observability/`, `task2-stt-benchmark/`,
   `task3-harness-artifact/`, `tools/`, `tests/`, `.github/workflows/`.
5. The commit history since your last snapshot. Several commits are retractions
   — they are the most informative objects in the repository.

Two files are quarantined and must never be quoted verbatim in your output:
`TRACE-orchestration.md` and any `TRACE-*-quarantined.md`. They carry unrelated
client identifiers, and your plan gets pasted into agent sessions whose traces
are published. Describe them in your own words if needed.

## What changed since round two

Verify each against the repository rather than accepting it:

- **Task 2's corpus was replaced.** The previous corpus had no independent
  reference, so the published report ran three engines and named no winner. The
  corpus is now a Russian conference talk that has a **human transcript
  published by the source** — an independent reference that no engine under test
  produced. Judge whether the amendment is properly dated and pre-output, whether
  the alignment of transcript to audio is sound, and whether the report's
  treatment of the transcript's known editing (fillers removed, grammar
  smoothed) is honest and measured rather than asserted.
- **Task 3's artifact was fixed upstream**, not just in the submission copy, and
  provenance re-verified. Check that the submitted file is still byte-identical
  to its published source, and whether the enforcement claim you flagged twice is
  now accurate rather than reworded around.
- **The exporter's fail-closed holes were closed** and the two override classes
  separated. Test the reasoning: can any content type still vanish while the
  header claims completeness?
- **Contradiction classes were made mechanically impossible** rather than swept
  by hand. Judge whether that is true or whether the same drift can recur.
- **Alerting semantics** were corrected for the pending/firing recurrence defect.

## Gaps we already know about

The team has stated these openly. Confirm they are the real list — and say so if
the self-assessment is itself incomplete, because a submission that
under-reports its own gaps is more dangerous than one that reports none:

- Task 1 and Task 2 traces are exported at session end and may still be absent.
- The six-hour observation snapshot is taken at or after 2026-08-23T22:14Z.
- Task 2 may not yet have five ranked engines or a published ranking.
- The repository still contains contaminated Git history; the rewrite runs once,
  last, after all sessions stop.

## What to produce

**Part 1 — Closure audit of round two.** Finding by finding: closed with
evidence, closed by assertion only, partially addressed, still open, or wrongly
closed — the last meaning a fix that does not do what its commit claims. Cite
files and SHAs. Retract any of your own findings that turned out to be wrong;
the repository contains agents disproving their own headline claims, and you
should hold yourself to that standard.

**Part 2 — New findings**, concentrated on the newest code, which has had the
least scrutiny: the corpus swap and transcript alignment, the engine adapters and
Modal execution path, the ranking and decision code, CI, and the packaging of the
submission. Separate what the repository proves from what an agent asserts.

**Part 3 — Requirement-by-requirement compliance table.** Walk `docs/TASK.md`
literally, one row per stated requirement across all three tasks and the global
principles, and mark each met / not met / unverifiable-from-here with the
evidence. Include the ones easy to overlook: `ts` carrying an offset, one JSON
object per physical line, a dashboard that opens with **no login**, the report
being **published** and reachable, "the code (a file)", "one file plus 2-3 lines",
and a **verbatim** trace per task.

**Part 4 — Submission verdict.** Submittable now, yes or no. If no, the ordered
minimum set of actions that makes it submittable, separating what must happen
before submission from what would merely be nice. Name anything already
irrecoverable.

**Part 5 — How a grader will read this.** They wrote the task and will read
dozens of these. Name the three things most likely to earn credit, the three most
likely to lose it, and — most useful — anything that is strong but currently
buried where a grader would not find it in their first two minutes.

Judge honesty as harshly as correctness. This submission's central claim is that
every conclusion carries the data behind it. Any place where that standard slips
— a number without a measurement, a status that outlived its evidence, a
limitation described with an adjective instead of a figure — is a finding, and a
more damaging one than a bug.
