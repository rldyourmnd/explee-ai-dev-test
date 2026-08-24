# Final plan to submission

**Status: COMPLETE — historical.** The plan that drove the run to submission, written 2026-08-23. Executed; kept as the record of how the work was directed, not as instructions.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


Written after the third external review, which confirmed every technical finding
I could check against the tree. This supersedes ad-hoc instructions: work this
document, in this order.

The organising principle: **this submission's identity is that every conclusion
carries its evidence.** Every remaining defect that damages us does so by
breaking that identity, not by being a bug. A wrong number is a mistake; a claim
we have already disproven in our own repository is a credibility failure.

---

## P0 — Submission blockers

### 0.1 Six-hour snapshot · `surface:2` · **now**

The mark passed at 22:14Z with no artifact. Take it without stopping collection:
first and last timestamp, proven span ≥ 21 600 s, maximum consecutive gap,
malformed count, provider count, lines, bytes, SHA-256, collector active before
and after. Commit. Continue collecting afterwards; the series repeats every six
hours and the submission ships the last one.

### 0.2 Clean alert artifact · `surface:2`

`ALERT-AUDIT.md` says `unreconciled lines: 2 of 13`, and one reads *caused solely
by a top_up … removing it removes the alert*. The task states in plain words that
top-ups are normal operations, not incidents. Shipping that file after proving it
wrong is worse than never auditing.

Deploy current source at the snapshot boundary, declare **T1** with the exact
commit SHA, replay a clean post-T1 window, regenerate `alerts.jsonl` from that one
configuration, re-run the field-by-field and counterfactual audit, and require
zero unreconciled lines and zero top-up-only or blip-only incidents. Point the
public `/alerts.jsonl` at the clean artifact.

### 0.3 Traces for Task 1 and Task 2 · `surface:2`, `surface:5`

Export in submission mode: no truncation, no lossy path, no blanket override, no
foreign project names, source session hash recorded, every failed attempt kept.
Export only when the session's real work is finished, or the trace stops before
the work does.

### 0.4 Stale top-level documents · `surface:3`

Each of these is currently false in the repository:

- Root `README.md` recommends `large-v3`. The report recommends prompted
  **`large-v3-turbo`**; the earlier recommendation was retracted in `21b9f68`.
- Root `README.md` says every task ships a trace. Two do not, yet.
- `task2-stt-benchmark/README.md` says corpus selection is pending, engine runs
  not started, report not started. All three are done and published.
- `data/analysis.json` describes the abandoned Radio-T corpus (`rt1027`, 120
  segments). Delete it or move it under an `archive/` path that says so.
- `docs/reviews/` is missing the second external review. Commit it; an audit
  chain with a hole in it invites the question of what else is missing.

---

## P1 — Task 2 methodological honesty

The narrow result survives scrutiny. The claims around it do not. Fix the claims;
do not touch the numbers to make them nicer.

### 1.1 Delete the false sentence · `surface:5`

The report says the decision was *run exactly as pre-declared*. It was not:
moving blocks, the 98% coverage rule, distractors and the final guardrail all
arrived after the freeze, and the guardrail arrived after outputs existed. Replace
with an explicit account of what was frozen, what was amended, when, and why. An
honest amendment table is a strength. That sentence, left standing, is the single
most damaging thing in the submission, because it makes a procedural claim we
cannot support in a document whose whole argument is procedural rigour.

### 1.2 Split the three outputs · `surface:5`

The freeze says default and tuned rankings are published separately and never
mixed. The current table mixes five default engines with two tuned Whisper
configurations. Publish three things:

1. **Default-engine ranking** — five engines, no prompt, like for like.
2. **Whisper prompt ablation** — within-family, large-v3 and turbo, stock versus
   prompted.
3. **Production recommendation** — drawn from both, stated as a configuration
   choice rather than as proof that Whisper beats engines that never received
   terminology assistance.

That third framing matters: only Whisper was tuned, so the tuned track cannot
establish engine superiority, only configuration superiority.

### 1.3 The recommendation becomes conditional and two-level · `surface:5`

My ruling, and the report should state it in these terms.

Prompted turbo reaches term recall 0.609 and plants fabricated terms in 5 of 99
segments, including writing `Kubernetics` over the real `Kubernetes`. Unprompted
turbo reaches 0.355 and fabricates nothing. In a meeting transcript a fabricated
term is worse than a missed one: a reader notices a gap from context, but cannot
tell an invented product name from a real one. Half the terminology is also a
real cost.

So recommend both, with the condition attached:

- **With terminology review in the loop:** prompted large-v3-turbo. Recall 0.609,
  expect roughly 5% of segments to carry a fabricated term that a reviewer must
  catch.
- **Without review:** unprompted large-v3-turbo. Nothing fabricated, and it will
  miss around two thirds of the technical terms.

And say the honest headline: no tested configuration is ready for unsupervised
use on this speech.

### 1.4 Replace the overstated generalisation · `surface:5`

Drop *prompting matters more than engine choice*. Only Whisper was prompted, and
the large-v3 gain came from collapsed transcripts. Replace with the corpus-bound
statement: on this corpus, the glossary prompt raised technical-term recall
substantially for both Whisper variants, and for turbo it did so without collapse
but at the cost of fabricated terms in 5 of 99 segments.

### 1.5 Guardrail: label it, then add independent guards · `surface:5`

The amended coverage guardrail excludes insertions, which stops charging engines
for speech the publisher edited out, and simultaneously means an engine can append
unlimited invented text and still pass. Prompted turbo sits at 0.394 insertion
rate while passing at 0.206.

Do not restore the old threshold, which rejects everything and produces no
recommendation. Instead label the current one as a **post-output amendment**, with
its date, reason and the fact that outputs existed, and add operational guards
that are not vulnerable to the same blind spot: collapsed-segment rate must be
zero, distractor-bearing segment rate must be reported against a declared ceiling,
and raw audio coverage must be ≥ 98%.

### 1.6 Make the code do what the report says · `surface:5`

- **Coverage must gate ranking.** `eligibility()` computes `rankable` and nobody
  filters on it before `decide()`. Filter. Compute coverage from raw returned
  segments against the manifest, not from generated reference blocks, because the
  latter always returns one score per block and cannot detect a missing segment.
  Add a test where an engine with < 98% raw files and a high apparent F1 is
  excluded.
- **Route the decision through moving-block.** `rank()`, `decide()` and the
  tie-break all call the independent-unit bootstrap; the moving-block comparison
  runs only afterwards. Reported coverage is 100%, so this will not move the
  numbers, which is precisely why it is cheap to fix and indefensible to leave.
  If any interval stays IID, label it IID in the table.

### 1.7 Commit the evidence · `surface:5`

The central numbers cannot be recomputed from the repository today. Commit, at
minimum as hashes with a manifest: the extracted reference and its hash, the
extraction manifest (source URL, retrieval time, page hash, selector rules, what
was removed, final counts), the glossary, a hash inventory of every raw stock and
tuned output, the distractor absence scan, and run parameters with model
revisions. No copyrighted audio needs publishing; the hashes and the recipe are
what make the result reproducible.

### 1.8 Two smaller corrections · `surface:5`

- wav2vec2 shows `term_f1: null` in JSON and `0.000` on the page. Pick one and
  explain it: zero produced terms against a reference containing terms is an
  operational zero, and that is defensible, but the two artifacts must agree.
- Describe the Parakeet slice result as a point estimate. The Russian-only slice
  is small and carries no interval, so *lowest observed WER on a small slice* is
  what the data support, not *best on Russian*.

---

## P2 — Surface what is already strong

The reviewer's most useful observation: our best evidence is buried.

- **`ALERT-AUDIT.md`** replays the window, compares every evidence field, runs
  top-up and blip counterfactuals, proves side-effect freedom by hashing the file
  before and after, and publishes a **failing** result. Link it from the root
  README and from the dashboard, where a grader meets it in the first two minutes.
- **The large-v3 retraction.** We recommended a configuration, found its score
  came from 19 collapsed transcripts, and withdrew it. That belongs in the report
  as a visible section, not in a commit message. Suggested heading: *What changed
  our mind*.
- **The power analysis** belongs beside the ranking, not deep in methodology: it
  is what stops a reader over-reading small differences.
- **Collector-first architecture** deserves one sentence at the top of the root
  README: we started the immutable collector before designing the monitor because
  the API has no history endpoint, so every later hypothesis is replayed against
  the same captured evidence.

---

## P3 — Delivery · `surface:3`

**Do not publish the working repository.** History carries quarantined
third-party identifiers, and a rewrite cannot retract clones or caches. Build a
fresh public submission repository with an allowlist, orphan history, and no
inherited objects. Verify by cloning it unauthenticated and scanning all refs for
the known identifiers, IP addresses and hostnames.

Gates run on the exact final SHA of that package: pytest, Ruff, and a type check
whose exclusions no longer hide Task 2 code. Record commands, tool versions and
exit codes. Branch protection is off, so a green run is evidence only if you
record it.

Final checklist before the human submits: dashboard opens in a clean profile;
report opens in a clean profile; six-hour snapshot committed with hashes; clean
`alerts.jsonl` with a passing audit; three traces present and lossless; package
scanned; gates green at the submitted SHA.

---

## What we are deliberately not doing

Named so nobody spends time on them, and so the report can say them out loud:

- A verbatim human transcript of a sample to measure publisher editing directly.
  We infer editing from insertion/deletion asymmetry and will say that it is
  inferred, not measured.
- Round-robin re-runs of engines already completed.
- A second multi-speaker corpus.
- Diarization and timestamp metrics: out of scope by decision, stated in the
  report.
- Rewriting the power simulation to generate F1 directly. It will be labelled a
  recall-driven exploratory simulation instead.
