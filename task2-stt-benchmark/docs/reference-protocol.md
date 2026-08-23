# Reference protocol — how the gold transcript actually gets made

Declared **before any draft was generated and before anyone listened to the
audio**. The policy in `docs/reference-policy.md` says what a correct
transcript looks like; this says who produces it, with what help, and how the
help's contamination is measured rather than assumed away.

## The constraint that shapes everything

The agent doing this work cannot hear. The only systems that can turn this
audio into text are the engines under test, and a reference derived from an
engine cannot then score that engine — it would measure agreement, not
accuracy. `harness/reference.py` refuses that combination outright and a test
asserts the refusal.

So the reference needs a human. What the tooling can do is make the human's
time buy as much reference quality as possible, and make what it does *not*
buy a published number.

## The protocol (option 3, approved 2026-08-23)

1. **Two drafting engines, both excluded from the ranking**, from different
   model lineages, transcribe all 120 segments.
2. **`harness.reference.disagreement_spans`** ranks segments by how much the
   two drafts disagree, densest first. Independent engines diverge where the
   audio is hard, so this is where an annotator's attention is worth most.
3. **A human corrects, working the ranked list top-down**, under the 12 policy
   rules, in the annotation workstation. Whatever time is available is spent on
   the segments where it buys the most.
4. **The from-scratch slice**: one annotator transcribes 6 segments completely
   unaided, without seeing any draft.
5. **`harness.reference.measure_residual_bias`** compares the unaided
   transcripts against the draft-assisted reference on exactly those segments.
   That difference is published as the reference's own error floor.

### The slice, fixed now

Selected by `select_scratch_slice`, seeded `20260823`, declared in the same
commit as this document and recomputable by any reader from the segment ids:

```
rt1027-0017  rt1027-0063  rt1027-0081
rt1027-0097  rt1027-0098  rt1027-0112
```

The selection is invariant to input order, so no one can reshuffle the manifest
until a convenient slice falls out. There is a test for that.

## What this buys and what it costs

**Buys:** a usable reference from hours of human time instead of a dozen, with
attention spent where errors concentrate.

**Costs, stated plainly:** an error that *both* drafting engines make is one the
correcting annotator never sees flagged, so it can survive into the reference.
Those shared errors are disproportionately the code-switching failures this
benchmark exists to measure — the very thing we are least able to afford. That
is precisely why step 4 exists: the from-scratch slice converts that unknown
into a measured rate, and `ResidualBias.sentence()` states it as the floor on
the benchmark's resolution. Engine differences smaller than the reference's own
error are reported as not separable.

The measurement is deliberately unflattering: every disagreement between the
unaided and draft-assisted transcripts is charged to the reference, including
disagreements that are really annotator slips. That makes the published number
an upper bound, which is the safe direction.

## Drafting-engine selection, and the lineage problem

Drafters must be strong, must disagree usefully, and must leave the ranking.
Both drafting engines are excluded from every published ranking.

The honest difficulty: every strong open model we would want as a drafter is
also one we would want to rank. Excluding the Whisper family to draft with it
would remove the baseline every reader knows. The chosen compromise is to draft
with lineages we are willing to lose from the ranking entirely, and to disclose
where a residual lineage overlap remains — for example, NeMo-trained models
share training corpora, so a NeMo drafter plausibly biases the reference toward
a NeMo rankee. Where such an overlap exists it is named in the report, and the
from-scratch slice is what bounds it.

## Graceful degradation

If the available human time is less than this protocol needs, we fall back to a
smaller **rigorously annotated** slice — fully independent double annotation
plus adjudication on fewer segments — rather than a larger sloppy one. Accuracy
metrics are then reported on that slice with honest intervals, while cost,
latency, retries and failure counts continue to be measured across the full
hour for every engine, because the task requires the same ~1 h of audio for all
of them.

Either way the report states, in the body: what was annotated, by whom, under
which policy, with what help, and what the measured residual bias was.

## Slate inversion (2026-08-23, human's ruling)

Everything must be free for the employer, and the employer's own funded Modal
account runs the GPU work. So open models on Modal are the **backbone** of the
slate, not a fallback:

* Whisper large-v3, Whisper large-v3-turbo
* Parakeet-TDT-0.6b-v3
* NVIDIA Canary
* GigaAM — Russian-specific, included precisely because it may be strong on
  Russian and weak on Latin-script terminology, which is a finding either way
* a multilingual audio LLM (Voxtral or Qwen2-Audio) if it runs cleanly

Cloud engines are added only where a genuinely free tier or free signup credit
exists. **Which cloud engines were attempted, and what their free limits
actually turned out to be, is recorded and published** — that record is itself
a finding, since the employer's own garbled transcripts are presumably produced
by a cloud engine.

No paid signups. If a free tier blocks an engine, the report names the specific
limit rather than dropping the engine silently.

The slate must reach 7+ so that removing two drafting engines still publishes
at least 5 ranked engines.
