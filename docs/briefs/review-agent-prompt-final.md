# Prompt for the external review agent — final round

**Status: COMPLETE — historical.** The final external-review prompt as issued. Its review is in `docs/reviews/`.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


Copy everything below the line.

---

You are running the **final** review on a hiring-test submission that is about to
be sent. Earlier rounds hunted defects and judged methodology. This round answers
one question: **is this ready to submit, and if not, exactly what stops it?**

You have GitHub access and public web access. You cannot run code or reach the
machines, so mark anything unverifiable as such rather than guessing.

## What is different this time

The repository is now **public**, with its **full commit history preserved**
after a rewrite that removed quarantined material. That was a deliberate choice:
the retraction chain is the submission's strongest evidence, and flattening it
would have deleted what a grader is most likely to find convincing. So you can
now inspect things earlier rounds could not:

- The complete commit history and its messages.
- CI runs attached to specific commits, under the GDS **Public OSS** programme:
  CodeQL, OSSF Scorecard, dependency review, secret scanning, gitleaks,
  actionlint, zizmor, harden-runner, SBOM and attestations, alongside the
  project's own pinned gates.
- The assembled `submission/` directory, which is exactly what the employer
  receives.

## Read in this order

1. `docs/TASK.md` — the **verbatim** task. The authority for every acceptance
   decision. Where our documents paraphrase it, the paraphrase is wrong.
2. `submission/` — the actual deliverables plus `NOTES.md`, the text going into
   the form's Notes field.
3. `docs/reviews/` — your three previous reviews and the methodology ruling.
4. `docs/ACCEPTANCE.md` — the acceptance matrix, which must be true at the final
   SHA.
5. The deliverables themselves, `tools/`, `tests/`, `.github/workflows/`.
6. The two public surfaces: `https://spend.nddev.it.com/` and
   `https://stt.nddev.it.com/`.

## What to produce

**Part 1 — Submission verdict.** Ready or not ready. If not ready, the ordered
list of what blocks it, separating hard blockers from things that merely improve
the odds. Be specific enough that each item can be closed without asking you a
follow-up question.

**Part 2 — Requirement compliance, walked literally.** One row per stated
requirement in `docs/TASK.md`, across all three tasks and the global principles,
marked met / not met / unverifiable with its evidence. Include the ones easy to
overlook: `ts` carrying an offset, one JSON object per physical line, a dashboard
that opens with **no login**, the report **published** and reachable, "the code
(a file)", "one file plus 2-3 lines", and a **verbatim** trace per task. Note
that one trace contains a documented, tool-generated excision where a tool result
listed unrelated projects; judge whether that is an honest solution or a
violation of the verbatim requirement, and say which and why.

**Part 3 — Closure of everything you raised.** Across all three previous rounds:
what is closed with evidence, closed by assertion, still open, or wrongly closed.
Retract any finding of yours that proved wrong.

**Part 4 — Adversarial pass on the claims that remain.** The submission makes
specific factual claims. Try to break the load-bearing ones: the six-hour
observation with no gaps, the alert audit passing with zero unreconciled lines,
the STT recommendation and the numbers behind it, the reference's independence,
and the provenance chain on the Task 3 artifact. For each, say what in the
repository would settle it and whether that evidence is actually present.

**Part 5 — How a grader reads this in ten minutes.** They wrote the task and will
read many of these. What earns credit, what loses it, and — most useful — what is
strong but buried where a grader would not find it. Include the `NOTES.md` text:
it is the one free-form channel to the reader, so judge whether it spends that
channel well.

## The standard to judge by

This submission's central claim is that every conclusion carries the data behind
it. Judge honesty as harshly as correctness. A number without a measurement, a
status that outlived its evidence, a limitation described with an adjective
instead of a figure, or a procedural claim the code does not support — each is a
finding, and a more damaging one than a bug, because it attacks the thing the
work is actually arguing.

Equally: say plainly where the work meets that standard. A final review that only
lists faults gives no signal about whether the whole is submittable.
