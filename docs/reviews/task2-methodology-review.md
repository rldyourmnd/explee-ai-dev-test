# Task 2 methodology review — adopted, rejected, and why

An external methodology review arrived for Task 2. This file is the ruling on it:
what we adopt, what we already had, and what we deliberately decline. It exists
so the decisions are auditable rather than absorbed silently.

The review's core argument is one we already agreed with — you cannot pick an STT
engine for code-switched Russian technical speech on WER alone — and our
pre-registration already encodes the shape it recommends: frozen design, strict
IT-term F1 as primary, WER as a guardrail, script sensitivity, separate default
and tuned tracks. What follows is where it goes further than we did.

## Adopted — corrects a real error

### 1. Paired moving-block bootstrap, not per-segment bootstrap

**This is a genuine methodological defect in our current code, not a refinement.**
Our bootstrap resamples segments independently. Segments from one talk are not
independent observations: same speaker, same microphone, same network path, same
topic, and terms recur in bursts. Treating 120 segments as 120 independent draws
overstates our confidence and can manufacture a significant difference that is
not there.

Fix: resample **contiguous blocks**, not segments.

```
primary_block_duration_s: 120        # 4 consecutive 30 s segments
sensitivity_block_duration_s: [60, 180, 300]
resamples: 10000
seed: 20260824
confidence: 0.95
```

Both compared systems must see the **same** resampled blocks. Ratios are
recomputed from pooled TP/FP/FN, never by averaging per-segment F1 — averaging a
ratio across segments is a different and wrong quantity.

Run the sensitivity ladder. If the winner changes with block size, the conclusion
is unstable and must be reported as unstable.

### 2. Distractor terms — cheap, and it measures the thing prompting breaks

Add ~10 terms to the tuned context that are **not spoken in the audio**, chosen
to resemble real ones: Lighthouse against ClickHouse, Kafdrop against Kafka,
Gravana against Grafana, Rake against RAG.

This measures whether terminology prompting makes an engine *invent* the term it
was told to expect. Recall gain alone is a half-truth: an engine that sprays
glossary terms wherever it is unsure looks excellent on recall and is useless in
a meeting transcript. Report:

```
distractor_segment_rate = segments containing an unspoken distractor / all segments
term_precision_delta    = precision_tuned - precision_default
term_recall_delta       = recall_tuned - recall_default
wer_delta               = wer_tuned - wer_default
```

Prompting counts as beneficial only if recall rises **and** precision does not
materially fall **and** WER does not worsen **and** distractors stay absent.

### 3. Coverage guardrail before ranking

```
successful_audio_coverage_min: 0.98    # at most 2 failed segments of 120
```

An engine that fails on hard audio must not be eligible to win. This closes the
survivorship hole from a second direction: we already fixed pairwise scoring, but
without an eligibility floor a flaky engine can still place well on the easy
remainder. Label it openly as an **operational policy**, not a measured finding.

### 4. Holm correction for multiple comparisons

Comparing a leader against seven others at α=0.05 without correction makes a
false positive likely. Apply Holm. State it in the pre-registration.

### 5. Raw-first persistence and round-robin request order

Before any parsing: store the complete raw response, `fsync`, hash it, record
request metadata — only then extract the transcript. A parse bug must never be
able to destroy the evidence.

Order requests round-robin with a randomised engine order per segment, rather
than running one engine across the corpus and then the next. Otherwise a transient
vendor slowdown or a model rollout lands entirely on one system and looks like
quality.

### 6. Power check before believing a null result

After the reference exists and before engine output: simulate systems differing
by 3, 5 and 10 percentage points, run the planned block bootstrap, and record the
detection probability. If one hour cannot separate 3–5 pp, say so in the report
rather than presenting "no significant difference" as if the test had power.

The corpus does **not** grow because a preferred engine lost. It grows only under
a rule written before results.

### 7. Slice analysis

Report per slice, not just overall: Russian-only, English technical terms, mixed
morphology (`ClickHouse-е`, `RAG-пайплайн`), code-switch boundaries, product and
vendor names, numbers and versions, fast speech, long silence, prompt distractors.

An engine that wins overall and loses the English-term slice is not the right
answer for this employer — and that is exactly the failure they described.

### 8. Native full-meeting track

Process the whole hour as production would: one long-form request where supported,
otherwise a single fixed pipeline segmentation. 120 independent 30-second requests
do not test boundary loss, duplication at joins, language drift over long context,
or hallucination accumulation in silence.

If time is short this is the first thing to cut — but cut it explicitly, and say
in the report that segment-level results may not transfer to long-form use.

## Already implemented

Frozen pre-registration before any output; strict script-sensitive IT-term F1 as
primary; WER as a guardrail rather than the decision; frozen hashed corpus and
manifest; separate default and tuned tracks; the ban on generic stemming (our
`Kafka`/`Kafko` fix); scoring raw output before normalisation; per-engine failure
accounting with pairwise intersections; the prohibition on deriving the reference
from a ranked engine.

## Declined, with the reason

**Two independent annotators plus adjudication.** Superseded by a better solution:
the corpus now carries a **human transcript published by the source**, independent
of every engine we rank. That removes the circularity the protocol was designed to
bound, at zero annotation cost. What replaces it is an obligation the review
itself implies — measure and publish how far that transcript departs from verbatim
speech, since published transcripts are edited for readability.

**cpWER, tcpWER, DER, JER, timestamp metrics.** Diarization is out of scope by
decision: the task asks which engine hears our speech correctly, not who spoke.
Scoring speaker attribution against a reference that does not validate it would be
worse than not scoring it. Stated as out of scope in the report.

**Blind human post-edit validation.** Methodologically sound, and it needs
annotators and hours we do not have. Named as a limitation.

**The proposed cloud slate** — OpenAI, Deepgram, ElevenLabs, Google Chirp. Nothing
paid, by decision; everything runs on our own Modal GPUs. The review's own open
models supply the slate: Qwen3-ASR, Parakeet-TDT-v3, GigaAM-v3, Whisper large-v3,
plus VibeVoice and Voxtral as long-form and realtime candidates. That is five or
more without a single paid account — and it means the employer can re-run the
whole benchmark themselves without buying anything, which is worth stating.

**Usability-calibrated WER threshold.** Deriving it needs historical meeting
transcripts rated by blind reviewers, which we do not have. Keep `WER ≤ 0.30` and
label it exactly as the review demands: a policy assumption, not a finding.

## One point where the review is right and it matters

Transliteration-tolerant scoring is defensible in the general code-switching
literature — but this employer's brief makes Cyrillic `РАКа` for RAG a failure by
definition. So the primary metric must stay script-sensitive, and any
transliteration-tolerant number is secondary diagnostics only. Our implementation
already does this; the point is that it must be *argued* in the report, not merely
done, because a reader who knows the literature will otherwise think we got it
wrong.
