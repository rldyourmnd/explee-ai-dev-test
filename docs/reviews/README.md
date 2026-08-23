# External reviews — the audit chain, including its gap

Three external review rounds were run against this repository. Two of them are
here as documents. **The second is not, and this file exists so that absence is
stated rather than discovered.**

| Round | Document | Status |
|---|---|---|
| 1 | [`external-review-2026-08-23T18-05Z.md`](external-review-2026-08-23T18-05Z.md) | committed |
| 2 | — | **no document exists** |
| 3 | [`../FINAL-PLAN.md`](../FINAL-PLAN.md) | committed as the ruling and work plan |
| Task 2 methodology | [`task2-methodology-review.md`](task2-methodology-review.md) | committed, with adopted and declined items recorded |

## Why round 2 has no file

Its findings reached this repository as rulings relayed in conversation and were
acted on — the acceptance matrix, `docs/ORCHESTRATION.md` and the commit history
between `fc2578` and `bf7baac` carry the work they produced. The review's own
text was never written to a file, and the orchestrator asked for it twice
without receiving one.

**Rather than leave the sequence looking like a missing artifact**, the gap is
recorded here. An audit chain with an unexplained hole invites the question of
what else is missing; an explained one does not. If the document turns up it
belongs at `docs/reviews/external-review-round2.md`, matching the naming above.

## What round 2 changed, from the work it produced

Recorded so the round is not simply absent from the record:

- Six live contradictions at `fc2578`, including a verification stamped 19:45Z
  inside a commit made at 19:43:14Z, and an acceptance baseline pointing at an
  older SHA than HEAD. Both classes are now blocked mechanically by
  `tools/repo_checks.py consistency`.
- The observation that our best evidence was buried — which is why
  `ALERT-AUDIT.md` is now linked from the first paragraph of the root README.
- The instruction to consolidate status into one source, which was **declined**
  under the scope rule: it would have made the repository more complete without
  changing anything we deliver or recommend.
