# Brief — Task 2: Pick the best transcriber for our meetings

**Status: COMPLETE — historical.** The Task 2 brief as issued to its agent. Delivered and published.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


You own Task 2 end to end. This session is one task, one trace: everything you do
here becomes `task2-stt-benchmark/TRACE.md`, exported verbatim at the end.

## Read first

1. `AGENTS.md` — rules 2 and 3 bind here too. You will handle API keys for
   several vendors: **environment variables only, never echoed, never pasted into
   a prompt**. A key printed once is a key published, because this trace ships.
2. `docs/reviews/external-review-2026-08-23T18-05Z.md`, section
   **Part 3 → `surface:5`**. That is your specification. Read Part 4 items 4 and
   5 as well, so you know exactly which decisions are not yours.
3. `README.md` and `docs/ORCHESTRATION.md` for where the submission stands.

## The ask, verbatim from the employer

> Our meeting transcripts are constantly garbled: the engine hears "РАКа" instead
> of RAG and "Lead House" instead of ClickHouse. Pick the best speech-to-text for
> our speech. We do not trust other people's benchmarks — their audio is not
> ours. The one hard condition: Russian speech with dense English and IT
> terminology mixed in — product names, tools, vendors, people, jargon
> (code-switching). This is exactly where the "universal" engines fall apart, and
> exactly what your test must catch. Build a comparison of ≥5 STT engines of your
> choice on the same audio (~1 hour), and the eval behind it — how you even
> measure "better/worse" on our kind of speech. **Designing the eval IS the task:
> we will not tell you the metric or hand you a recipe. Figuring out that a test
> is needed and how to make it defensible is half the evaluation.**

Deliverables: a published comparison report that opens with no login (the report
is the main artifact) plus `TRACE.md`.

## Two decisions are the human's, and they are still open

**Audio source** and **budget / which vendors may receive the audio**. Do not
choose either yourself, do not spend money, and do not upload audio anywhere
until they are answered. When the answer arrives it gets recorded at the top of
this file as the authorised corpus and spend ceiling.

## Start now anyway — on everything that does not depend on those answers

This is not a workaround. The evaluation design **must** be frozen before you see
any engine output, or the metric can be tuned, however unconsciously, to favour a
result. Pre-registering it is the methodologically correct order, and it happens
to be the whole critical path. Concretely, build now:

1. **The eval harness.** Ingestion, a segment manifest keyed by SHA-256, a
   per-engine adapter interface, raw-output storage before any normalisation,
   retry and failure accounting, and a results table written as CSV. Engines plug
   in behind one interface so a missing key blocks one adapter, not the run.
2. **The reference-transcript policy, written and committed before any audio
   exists.** Latin vs Cyrillic technical terms; product-name canonical spelling;
   numerals and abbreviations; filler words and false starts; punctuation;
   unintelligible spans; speaker labels; English inflections inside Russian
   grammar (`в ClickHouse`, `задеплоили Worker`, `пересобрали RAG-пайплайн`).
   Every rule needs a worked example of a pass and a fail.
3. **The metric implementation**, with unit tests against hand-built fixtures:
   normalised WER; CER; WER restricted to code-switched spans; exact IT-term
   precision, recall and F1; product/vendor name recall; Latin-to-Cyrillic
   substitution rate; hallucination rate; omission rate; code-switch boundary
   error rate; speaker attribution and timestamp quality. Fixtures should include
   the employer's own examples — `РАКа` for RAG, `Lead House` for ClickHouse —
   and assert those score as failures.
4. **Paired bootstrap confidence intervals** over segments, plus the reporting
   rule for when the data does **not** establish a winner. Saying two engines are
   statistically indistinguishable and choosing on cost is a stronger result than
   inventing a ranking the data does not support.
5. **The decision rule, pre-declared.** Which metric is primary, what guardrail
   the overall WER must satisfy, and the tie-break order. Declare it before you
   have results, and say plainly that it was declared in advance — a threshold
   chosen after seeing the numbers is not evidence.
6. **The glossary**, fixed before scoring: the IT terms whose recognition you
   will measure. Do not extend it after hearing engine output.

## Fairness rules that decide whether the comparison means anything

Identical source audio, identical segmentation boundaries, identical resampling,
channel handling and retry policy for every engine. Score raw output; any
normalisation applies equally to all. Never compare one engine with a glossary
against another engine's default — publish **two separate rankings**,
default-model and terminology-assisted, and say which configuration each vendor
actually supports.

Record for every run: exact model identifier and snapshot date, every request
parameter, wall-clock latency, retries, failed segments, and actual billed cost.
Marketing prices are not measurements.

## Engine slate

Run at least six so one broken account does not drop the benchmark below the
required five. Defensible slate, subject to the human's budget answer: OpenAI GPT
Transcribe, Deepgram Nova-3 multilingual, Google Chirp 3, ElevenLabs Scribe v2,
Azure Speech, Speechmatics. A local baseline via Whisper large-v3 or Parakeet is
worth adding — fully reproducible, no vendor adaptation, and it costs nothing to
be honest about.

Vendor claims about code-switching are hypotheses to test, not facts to cite.
Deepgram documents Russian/English code-switching; ElevenLabs exposes keyterm
prompting; OpenAI exposes keyword and multiple language hints. Measure all of it.

## Definition of done

- ≥5 engines on identical ~1 h audio, with the corpus frozen and hashed.
- Reference transcript verified by a human, under a policy published beforehand.
- Default and tuned tracks reported separately.
- WER supplemented by term-level and code-switch metrics.
- Confidence intervals present; cost and latency measured, not quoted.
- Winner selected by the pre-declared rule; limitations listed explicitly.
- Report opens in incognito with no login.
- `TRACE.md` exported with **no result truncation** — do not use `--max-result`.

Do not touch `task1-*` or `task3-*`. Report milestones and blockers to the
orchestrator.
