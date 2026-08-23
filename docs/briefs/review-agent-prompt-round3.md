# Prompt for the external review agent — round 3

Copy everything below the line.

---

You are running the **third** review round on a hiring-test submission that is
close to delivery. Rounds one and two hunted defects. This round has two jobs:
decide whether the work is submittable, and **attack the conclusions it now
makes**, because for the first time there are real results to be wrong about.

You have authenticated read-only access to GitHub through the owner's connector,
plus public web access. You cannot run code, reach the machines, or see the
agents' screens — say so explicitly wherever a conclusion would need something
you cannot observe.

## Repository and surfaces

`https://github.com/rldyourmnd/explee-ai-dev-test` — review current `main`.

Two public pages you **can** check independently, and should:

- `https://spend.nddev.it.com/` — the Task 1 dashboard.
- `https://stt.nddev.it.com/` — the Task 2 comparison report.

Read, in this order: `docs/TASK.md` (the **verbatim** task — the authority for
every acceptance decision; where our documents paraphrase it, the paraphrase is
wrong), your own two previous reviews in `docs/reviews/`,
`docs/reviews/task2-methodology-review.md` (our ruling on an external methodology
review — what we adopted and what we declined, with reasons),
`docs/ACCEPTANCE.md`, `docs/ORCHESTRATION.md`, then the deliverables and the
commit history since your last snapshot.

Two files are quarantined and must never be quoted verbatim in your output:
`TRACE-orchestration.md` and any `TRACE-*-quarantined.md`. They carry unrelated
client identifiers, and your plan gets pasted into agent sessions whose traces
are published. Describe them in your own words if needed.

## What changed since round two

Verify each rather than accepting it:

- **Task 2 now has results.** Five engines — Whisper large-v3, Whisper
  large-v3-turbo, Parakeet-TDT-v3, SeamlessM4T-v2, wav2vec2-XLSR-ru — scored
  against a **human transcript published by the conference itself**, so the
  reference was produced by neither us nor any ranked engine. The report names a
  production recommendation: Whisper large-v3 with a glossary prompt.
- **A methodology review was adopted in part**: paired moving-block bootstrap
  replacing per-segment resampling, distractor terms, a 98% coverage eligibility
  guardrail, Holm correction, raw-first persistence, round-robin ordering, slice
  analysis, power simulation. Declined items are listed with reasons in
  `docs/reviews/task2-methodology-review.md`.
- **Task 3 is complete**, including an exported trace, with the artifact's
  enforcement overclaim fixed **upstream** and provenance re-verified.
- **Task 1** closed every round-two finding and now collects past six hours by
  decision, taking a numbered snapshot every six hours.

## Known gaps, stated by the team

Confirm this is the real list — and say so if the self-assessment is itself
incomplete, because a submission that under-reports its own gaps is more
dangerous than one that reports none:

Task 1 and Task 2 traces not yet exported; the six-hour snapshot due at
2026-08-23T22:14Z; the T1 clean-window regeneration not yet run; `monitor.py`
not yet single-file; the contaminated Git history not yet rewritten.

## What to produce

**Part 1 — Closure audit of round two.** Finding by finding: closed with
evidence, closed by assertion only, partially addressed, still open, or wrongly
closed — the last meaning a fix that does not do what its commit claims. Cite
files and SHAs. Retract any of your own findings that proved wrong.

**Part 2 — Adversarial audit of the Task 2 conclusion.** This is the most
valuable thing you can do this round. The report claims Whisper large-v3 with a
glossary prompt is the production choice, that prompting matters more than engine
choice (term recall 0.40 → 0.63), that turbo hallucinated distractor terms
including writing `Kubernetics` over the real `Kubernetes`, and that Parakeet has
the best Russian-only WER while placing third on code-switched speech. **Try to
break each of those.** Specifically:

- Does the moving-block bootstrap actually resample contiguous blocks, draw the
  same blocks for both compared systems, and pool counts rather than averaging
  per-segment ratios?
- Is the reference genuinely independent, and is the publisher transcript's known
  editing (fillers removed, grammar smoothed) *measured* and reported, or merely
  acknowledged? An inflated absolute WER is fine if disclosed; an undisclosed one
  is not.
- Does transcript-to-audio alignment introduce a bias that favours any engine —
  for instance, one whose output conventions resemble the transcript's editing?
- Are the distractor terms verified absent from the reference **and** from stock
  outputs before the run, or asserted to be?
- Does the coverage guardrail actually gate ranking eligibility in code?
- Is the tuned-versus-default comparison like-for-like, and is the recommendation
  drawn from a track that all engines could enter?
- Does the power analysis support the strength of the claims, or are differences
  being read from a corpus that cannot resolve them?

Where you cannot verify without running code, say so — but state what evidence in
the repository would settle it.

**Part 3 — Requirement-by-requirement compliance table.** Walk `docs/TASK.md`
literally: one row per stated requirement across all three tasks and the global
principles, marked met / not met / unverifiable-from-here with the evidence.
Include the easily-missed ones: `ts` carrying an offset, one JSON object per
physical line, a dashboard that opens with **no login**, the report **published**
and reachable, "the code (a file)", "one file plus 2-3 lines", and a **verbatim**
trace per task.

**Part 4 — Submission verdict.** Submittable, yes or no. If no, the ordered
minimum set of actions that makes it so, separating what must happen before
submission from what is merely desirable. Name anything already irrecoverable.

**Part 5 — How a grader will read this.** They wrote the task and will read many
of these. Name the three things most likely to earn credit, the three most likely
to lose it, and — most useful — anything strong that is currently **buried** where
a grader would not find it in their first two minutes.

Judge honesty as harshly as correctness. This submission's central claim is that
every conclusion carries the data behind it. Any place where that slips — a
number without a measurement, a status that outlived its evidence, a limitation
described with an adjective instead of a figure — is a finding, and a more
damaging one than a bug.
