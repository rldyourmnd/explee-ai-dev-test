# Pre-registration — STT benchmark evaluation design

**Status: FROZEN 2026-08-23T19:30Z.** Declared before any corpus was selected,
before any engine was called, and before any engine output existed in this
repository. Nothing below may be changed after the first engine result is read.
If something here turns out to be wrong, the amendment is recorded as an
amendment — dated, justified, and reported alongside the original — never as a
silent edit.

That order is the whole point. A threshold chosen after seeing the numbers is
not evidence; it is a description of the numbers. This file exists so that a
reader can check we did not choose ours that way.

## 1. What is being decided

Which speech-to-text engine to use for this company's internal meetings:
Russian speech with dense English IT terminology, code-switching inside
sentences, several speakers, real room acoustics.

The employer's two reported failures define success: an engine that hears
`РАКа` for RAG and `Lead House` for ClickHouse is unusable no matter what its
word-error rate says. Both are encoded as test fixtures
(`tests/test_task2_metrics.py`) and asserted to score as failures.

## 2. Primary metric

**IT-term F1** — exact recognition of the frozen glossary terms
(`glossary.json`, SHA-256 recorded at run time), precision and recall pooled
over the corpus.

Why F1 and not WER: WER weights `ну` and `ClickHouse` identically. A transcript
that garbles every product name but nails the filler words scores well on WER
and is worthless in a meeting, because the terms are what a reader searches for
and what changes the meaning of a decision. F1 rather than recall alone, because
recall alone rewards an engine that sprays glossary terms everywhere.

## 3. Guardrail

**Overall normalised WER ≤ 0.30** on the frozen corpus.

An engine that fails this guardrail is excluded regardless of its term F1. The
purpose is to reject an engine that gets the terminology right inside an
otherwise unreadable transcript. The value is set before seeing any result and
is chosen as roughly the level above which a Russian meeting transcript stops
being usable as a written record; it is a usability floor, not a target.

If **no** engine clears the guardrail, that is the finding, reported as such.

## 4. Tie-break order

Applied only when the paired bootstrap on the primary metric cannot separate
two engines — that is, when the 95 % interval on the difference contains 0.

1. **Code-switched-span WER** (`cs_wer`), lower wins — measured only where the
   speech actually switches language.
2. **Latin-to-Cyrillic substitution rate**, lower wins — the `РАКа` failure
   mode, measured directly.
3. **Hallucination rate**, lower wins — an invented sentence in a meeting record
   is worse than a missing one, because it is indistinguishable from a real one.
4. **Measured cost per hour of audio**, lower wins — from billed figures where
   the vendor exposes them, otherwise from the vendor's own tariff applied to
   measured duration and labelled as a tariff calculation, not a measurement.
5. **Median latency per segment**, lower wins.

At each step the comparison is again a paired bootstrap; a step that also cannot
separate the engines passes to the next. If every step is indistinguishable, the
report says the data do not establish a winner between those engines and
recommends the cheaper one on cost grounds alone, saying plainly that the choice
is not a quality judgement.

## 5. Statistics

* Paired bootstrap over **segments**, 10 000 resamples, seed `20260823`,
  95 % percentile intervals (`harness/bootstrap.py`).
* Pairing is enforced: the same segment ids in the same order, or the call
  raises. Two engines transcribing the same hour are not independent samples.
* Pooled metrics are computed from **summed counts**, never as a mean of
  per-segment rates.
* Only segments that **every** compared engine transcribed successfully enter
  the comparison. Failed segments are reported separately, with counts, and are
  never imputed as empty strings.
* A metric with no observations is reported as unmeasured, never as `0.0`.

## 6. Two rankings, never mixed

* **Default track** — stock model, no terminology assistance.
* **Tuned track** — vendor terminology assistance (keyterm prompting, custom
  vocabulary, phrase hints) supplied with the *same frozen glossary* for every
  vendor that supports it.

They are published as two separate tables. Comparing one engine's tuned run
against another's default run would be a comparison of configurations, not of
engines. Vendors with no terminology feature appear in the default table only,
and the report says the feature is absent rather than showing an empty cell.

## 7. Fairness controls

Byte-identical segment files for every engine, cut once by `harness/manifest.py`
at 16 kHz mono `pcm_s16le`; identical segmentation boundaries; identical retry
policy (4 attempts, 1/4/10 s backoff) applied by the runner, not by adapters;
raw vendor output stored and hashed before any normalisation; identical
normalisation applied to reference and to every hypothesis.

Recorded per run: exact model identifier, snapshot date, every request
parameter, wall-clock latency, retry count, failed segments, and billed cost
where exposed.

## 8. Engine slate

Target ≥ 6 so that one broken account cannot drop the benchmark below the
required 5. Under the current envelope — public or already-permitted audio, free
tiers, existing credits, self-hosted inference; **no new spending without the
human** — the slate is:

| Engine | Access route under this envelope | Terminology track |
|---|---|---|
| Whisper large-v3 (self-hosted) | local inference, no account, fully reproducible | initial-prompt biasing |
| Parakeet / NeMo (self-hosted) | local inference, no account | none |
| Deepgram Nova-3 multilingual | free credit on signup | keyterm prompting |
| OpenAI GPT Transcribe | existing credit | prompt / keyword hints |
| ElevenLabs Scribe v2 | free tier | keyterm prompting |
| Speechmatics | free trial tier | custom dictionary |
| Google Chirp 3 | free tier, if reachable without new payment details | phrase sets |
| Azure Speech | free tier, if reachable without new payment details | phrase lists |

The two self-hosted engines are the floor: they need no account, no payment
details and no vendor permission, so the benchmark cannot fall below two engines
under any account failure. If the total reachable within the envelope falls
below five, the report names the specific blocker per engine — which account,
which requirement — rather than quietly reporting four.

Vendor claims about code-switching are hypotheses under test here, not evidence
to cite.

## 9. Corpus conditions

Fixed before selection, so that the corpus cannot be chosen to suit an engine:

* Natural Russian speech, ~1 hour, **not** scripted or synthetic.
* Dense English IT terminology with code-switching **inside** sentences.
* More than one speaker, with real acoustics (overlap, room, varying levels).
* Publication rights that allow us to cite the source, so a grader can fetch the
  same recording and re-run the harness against it.
* Frozen before any engine runs: original file preserved, SHA-256 recorded,
  duration, sample rate, channel layout and speaker count probed and recorded,
  and a segment manifest hashed per segment.

## 10. What would falsify the conclusion

Stated in advance, so the limitations section is not written to fit the result:

* One hour of one meeting is one acoustic condition and one set of voices. A
  different room, or speakers with different accents, could reorder engines.
* The glossary is this company's vocabulary. Term F1 does not transfer to a
  company with a different stack.
* Free-tier endpoints may not be the same deployments as paid ones; where that
  is known or suspected it is stated.
* Inter-annotator WER bounds the resolution of the whole exercise: engines
  closer together than the reference's own uncertainty are not separable, and
  will be reported as inseparable.

## 11. Frozen artefacts

| Artefact | Frozen at | Verified by |
|---|---|---|
| `glossary.json` | 2026-08-23T19:05Z | SHA-256 recorded in every run report |
| `docs/reference-policy.md` | 2026-08-23T19:20Z | committed before corpus selection |
| this file | 2026-08-23T19:30Z | committed before the first engine call |
| metric implementation + tests | 2026-08-23T19:15Z | `tests/test_task2_*.py`, 44 tests |
| corpus manifest | pending selection | `harness/manifest.py`, hashed per segment |
