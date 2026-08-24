# Reference-transcript policy

**Status: FROZEN, commit `9fd6ff8`, 2026-08-23T19:00:14Z. Written and committed
before any audio was selected and before any engine output existed.** The date
is the commit's, read from git rather than typed here; see
`PREREGISTRATION.md` §12 for why that distinction is not pedantry.

A word-error rate is a comparison against a reference, so the reference *is* the
metric. Written after hearing the audio, this document would be a description of
what one annotator happened to type; written before, it is a rule the annotators
and the scorer both have to obey. Every rule below therefore carries a worked
pass and a worked fail, so a disagreement between annotators has an answer that
does not depend on who is arguing.

## How the reference is produced

1. Two annotators transcribe every segment independently, under this policy,
   without seeing any engine output. Engine output is not used as a first draft:
   a corrected engine transcript is biased towards that engine.
2. Segments where the two disagree after normalisation are adjudicated by a
   third pass, and the adjudicated decision is recorded with the rule number it
   applied.
3. Inter-annotator agreement (WER between the two independent passes) is
   published. If it is worse than the gap between the top engines, the benchmark
   cannot separate those engines and says so.
4. The final reference is hashed; the hash goes in the report.

## Rules

### R1: Latin-script technical terms are written in Latin script

A term spoken in English keeps its English spelling and its canonical casing,
inside Russian grammar.

* **Pass:** speaker says *«перенесли витрину в кликхаус»* → reference reads
  `перенесли витрину в ClickHouse`.
* **Fail:** reference reads `перенесли витрину в Кликхаус`. Cyrillicising the
  term hides the exact failure the benchmark exists to measure.

### R2: Product and vendor names use the vendor's own canonical spelling

`ClickHouse`, `OpenSearch`, `pgvector`, `LangChain`, internal capitals and all.
Casing is folded away before scoring, so this rule costs nothing at scoring time
and keeps the reference readable and reviewable.

* **Pass:** `подняли OpenSearch рядом с Elasticsearch`.
* **Fail:** `подняли opensearch рядом с elastic search`. The second form is a
  different token sequence and would silently redefine what counts as correct.

### R3: Terms that are genuinely spoken as Russian words are written in Cyrillic

Some terms have entered Russian as Russian words: `апи`, `деплой`, `прод`,
`эмбеддинг`, `промпт`, `кубер`. Write what was said. The glossary accepts these
Cyrillic forms explicitly, and the exception list is exactly the `accept` arrays
in `glossary.json`, and it is not extended by an annotator mid-pass.

* **Pass:** speaker says *«задеплоили на прод»* → `задеплоили на прод`.
* **Fail:** `задеплоили на prod`. The speaker did not code-switch here, and
  recording a switch that did not happen corrupts the code-switch metric.

### R4: English stems inflected by Russian grammar keep the stem, and the ending is written as heard

* **Pass:** `в ClickHouse-е`, `задеплоили Worker`, `пересобрали RAG-пайплайн`,
  `положили в Kafkу`.
* **Fail:** `в Кликхаусе`, `задеплоили воркер`, `пересобрали РАГ-пайплайн`.

Scoring folds the inflection: `harness.normalize.normalize_term` strips the
Russian tail and folds the Latin stem, so `ClickHouse`, `ClickHouse-е` and
`ClickHouseе` are one term. The hyphen is a token boundary for WER, so a
hyphenation disagreement between annotators costs nothing.

### R5: Numerals are written as digits; measurement units are written as spoken

* **Pass:** *«около трёхсот миллисекунд»* → `около 300 миллисекунд`;
  *«пятьдесят процентов»* → `50 процентов`.
* **Fail:** `около трёхсот миллисекунд` (word form) or `50%` (symbol). Both are
  defensible in isolation; only one can be the rule, and mixing them makes every
  engine's numeral handling unscoreable.

Ordinals and years keep their Russian written form when spoken as words:
*«в двадцать четвёртом»* → `в 2024`.

### R6: Abbreviations are written unspaced in their canonical script

* **Pass:** `API`, `SLA`, `CI/CD`, `S3`, `GPU`, `LLM`.
* **Fail:** `A P I`, `эс три`, `си ай си ди`. Letter-by-letter spelling is how
  the letters are *pronounced*, not how the abbreviation is written; scoring
  folds `S3` and `s 3` to the same term, so nothing is lost.

### R7: Filler words and false starts are transcribed, verbatim, once

Fillers (`ну`, `вот`, `значит`, `э-э`) are written. A repeated false start is
written as spoken: *«мы ре— мы решили»* → `мы ре мы решили`. The dash inside
that example is data, not prose: it marks where the speaker cut themselves off,
and it is the only em dash left in this directory for that reason.

* **Pass:** `ну вот мы значит подняли Kubernetes`.
* **Fail:** `мы подняли Kubernetes`. Silently tidying the reference makes an
  engine that drops fillers look perfect and one that transcribes them look
  wrong. Both behaviours are legitimate; the report separates them by showing
  omission rate next to WER rather than by editing the reference.

### R8: Punctuation is written for readability and is not scored

Sentence punctuation and capitalisation are stripped before scoring
(`normalize_for_wer`). They are still written, because an unpunctuated reference
cannot be reviewed by a human, and because punctuation quality is reported
separately as a qualitative note, not folded into WER.

* **Pass:** `Мы подняли ClickHouse. Стало быстрее.` scores identically to
  `мы подняли clickhouse стало быстрее`.
* **Fail:** treating a missing comma as a word error.

### R9: Unintelligible spans are marked, and excluded from scoring

A span neither annotator can resolve is written `[unintelligible]`. Segments
whose unintelligible share exceeds 10 % of tokens are excluded from the corpus
entirely, before any engine sees them, and the exclusion is published with the
count.

* **Pass:** `и тогда мы [unintelligible] переключили трафик`.
* **Fail:** guessing a plausible word. A guessed reference charges every engine
  for the annotator's invention, and rewards the engine that guessed the same.

### R10: Speaker labels are stable across the whole corpus

Speakers are `S1`, `S2`, … assigned in order of first utterance and fixed for
the entire hour. Overlapping speech is attributed to the speaker who is
intelligible; if both are, the span is split at the word.

* **Pass:** the same person is `S2` in minute 3 and in minute 47.
* **Fail:** per-segment labels. Scoring resolves the engine's labels to the
  reference's globally, once, so an engine that renumbers speakers every segment
  scores badly, which is the correct outcome, and only possible if the
  reference itself is globally consistent.

### R11: Timestamps come from the segment manifest, not from an annotator

Word onsets in the reference are taken from forced alignment against the frozen
segment audio, and are offset by the segment start recorded in the manifest.
Annotators do not type timestamps.

* **Pass:** a word at 4.2 s into segment `c-0007` (starting at 210.0 s) has
  reference onset `214.2`.
* **Fail:** hand-typed onsets, which have worse resolution than the engines
  being measured and would make the timestamp metric a measurement of the
  annotator.

### R12: Translation is never transcription

If a speaker says `rollback`, the reference says `rollback`, never `откат`, and
the glossary does not accept the translation as a hit.

* **Pass:** `сделали rollback за пятнадцать минут` → `сделали rollback за 15
  минут`.
* **Fail:** `сделали откат за 15 минут`.

## What this policy does not decide

The audio itself. Provenance, consent, and which vendors may receive it are the
human's decisions (external review, Part 4 items 4 and 5), recorded in
`docs/briefs/task2.md` when they arrive. This policy is written to apply to
whichever corpus is authorised.
