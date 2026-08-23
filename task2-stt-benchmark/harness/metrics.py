"""Metrics for Russian speech with dense English IT terminology.

Why not WER alone. WER treats every word as equally important. In a meeting
transcript it is not: a dropped `ну` costs nothing, while `РАКа` for RAG and
`Lead House` for ClickHouse make the sentence unusable and change what the
reader believes was decided. An engine can win on WER and still be the wrong
choice for this speech. So WER is reported as a guardrail, and the metrics that
decide the ranking are term-level and code-switch-level.

Every metric here returns **counts**, not ratios. Ratios are formed only when
pooling (`aggregate`), because a mean of per-segment WERs is not the WER of the
corpus, and because the paired bootstrap must resample counts.

All metrics are computed from one alignment per segment (`harness.align`) so
the per-category numbers are mutually consistent by construction.

Stdlib only.
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from .align import Alignment, align, find_ngram
from .glossary import Glossary, Term
from .normalize import characters, normalize_term, script_of, tokens

# How far from the reference position a term may appear in the hypothesis and
# still count as recognised. Three tokens absorbs ordinary alignment jitter
# without letting a term spoken elsewhere in the segment earn credit.
TERM_WINDOW = 3

# A hypothesis word onset within this many seconds of the reference onset is
# counted as correctly timed. 0.5 s is below the threshold at which a reader
# scrubbing a recording lands on the wrong sentence.
TIMESTAMP_TOLERANCE_S = 0.5


@dataclass(frozen=True)
class Word:
    text: str
    start: float | None = None
    end: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class Transcript:
    """A reference or hypothesis transcript for one segment.

    `words` is optional: an engine that returns no word timings or no speaker
    labels still gets scored on every text metric, and its missing capability
    is reported as missing rather than as a zero.
    """

    text: str = ""
    words: tuple[Word, ...] = ()

    @classmethod
    def from_words(cls, words: Sequence[Word]) -> "Transcript":
        return cls(text=" ".join(w.text for w in words), words=tuple(words))

    @property
    def has_timings(self) -> bool:
        return any(w.start is not None for w in self.words)

    @property
    def has_speakers(self) -> bool:
        return any(w.speaker is not None for w in self.words)


@dataclass
class TokenStream:
    tokens: list[str]
    terms: list[str]
    starts: list[float | None]
    speakers: list[str | None]


def token_stream(transcript: Transcript) -> TokenStream:
    """Flatten a transcript to parallel token / term / timing / speaker lists.

    One word may normalise to several tokens (`RAG-пайплайн` -> `rag`,
    `пайплайн`); each inherits the word's timing and speaker. Index `i` means
    the same thing in every list, which is what lets one alignment drive all
    the metrics.
    """
    stream = TokenStream([], [], [], [])
    if transcript.words:
        for word in transcript.words:
            word_tokens = tokens(word.text)
            term_tokens = normalize_term(word.text).split()
            if len(term_tokens) != len(word_tokens):
                # normalize_term maps token-for-token; a mismatch means the
                # invariant broke and every downstream index would be wrong.
                raise AssertionError(f"token/term length mismatch on {word.text!r}")
            for tok, term in zip(word_tokens, term_tokens):
                stream.tokens.append(tok)
                stream.terms.append(term)
                stream.starts.append(word.start)
                stream.speakers.append(word.speaker)
    else:
        stream.tokens = tokens(transcript.text)
        stream.terms = normalize_term(transcript.text).split()
        stream.starts = [None] * len(stream.tokens)
        stream.speakers = [None] * len(stream.tokens)
    return stream


@dataclass
class SegmentScore:
    """Raw counts for one segment and one engine. Ratios come later."""

    segment_id: str
    engine: str

    ref_words: int = 0
    hits: int = 0
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0

    ref_chars: int = 0
    char_edits: int = 0

    cs_ref_words: int = 0
    cs_errors: int = 0

    term_ref_occurrences: int = 0
    term_hyp_occurrences: int = 0
    term_hits: int = 0

    name_ref_occurrences: int = 0
    name_hits: int = 0

    latin_term_occurrences: int = 0
    latin_to_cyrillic: int = 0

    boundaries: int = 0
    boundary_errors: int = 0

    speaker_scored_tokens: int = 0
    speaker_confusion: Counter = field(default_factory=Counter)

    timestamp_deltas: list[float] = field(default_factory=list)
    timestamp_within_tolerance: int = 0

    has_timings: bool = False
    has_speakers: bool = False

    missed_terms: list[str] = field(default_factory=list)
    misrecognitions: list[tuple[str, str]] = field(default_factory=list)


def _term_occurrences(
    term_tokens: Sequence[str], glossary: Glossary
) -> list[tuple[int, int, Term, str]]:
    """Non-overlapping, leftmost-longest glossary occurrences.

    Longest-first so `feature store` is one occurrence rather than a miss plus
    whatever a shorter variant would have matched.
    """
    found: list[tuple[int, int, Term, str]] = []
    for term in glossary:
        for variant in term.variants:
            for start, end in find_ngram(term_tokens, variant):
                found.append((start, end, term, script_of(" ".join(variant))))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    chosen: list[tuple[int, int, Term, str]] = []
    occupied = -1
    for start, end, term, script in found:
        if start > occupied:
            chosen.append((start, end, term, script))
            occupied = end - 1
    return chosen


def _code_switch_spans(token_list: Sequence[str]) -> list[tuple[int, int]]:
    """Maximal runs of Latin-script (or mixed-script) reference tokens."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, tok in enumerate(token_list):
        if script_of(tok) in ("latin", "mixed"):
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(token_list)))
    return spans


def score_segment(
    segment_id: str,
    engine: str,
    reference: Transcript,
    hypothesis: Transcript,
    glossary: Glossary,
) -> SegmentScore:
    """Score one engine on one segment. Pure function of its inputs."""
    ref = token_stream(reference)
    hyp = token_stream(hypothesis)
    alignment = align(ref.tokens, hyp.tokens)
    r2h = alignment.ref_to_hyp()

    score = SegmentScore(segment_id=segment_id, engine=engine)
    score.ref_words = alignment.ref_length
    score.hits = alignment.hits
    score.substitutions = alignment.substitutions
    score.deletions = alignment.deletions
    score.insertions = alignment.insertions
    score.has_timings = hypothesis.has_timings
    score.has_speakers = hypothesis.has_speakers

    ref_chars = characters(reference.text if not reference.words else " ".join(w.text for w in reference.words))
    hyp_chars = characters(hypothesis.text if not hypothesis.words else " ".join(w.text for w in hypothesis.words))
    char_alignment = align(ref_chars, hyp_chars)
    score.ref_chars = len(ref_chars)
    score.char_edits = (
        char_alignment.substitutions + char_alignment.deletions + char_alignment.insertions
    )

    _score_code_switch(score, alignment, ref.tokens, r2h)
    _score_terms(score, ref, hyp, r2h, glossary)
    _score_speakers(score, alignment, ref, hyp)
    _score_timestamps(score, alignment, ref, hyp)
    return score


def _score_code_switch(
    score: SegmentScore,
    alignment: Alignment,
    ref_tokens: Sequence[str],
    r2h: dict[int, int | None],
) -> None:
    spans = _code_switch_spans(ref_tokens)
    in_span = {i for start, end in spans for i in range(start, end)}
    score.cs_ref_words = len(in_span)
    for edit in alignment.edits:
        if edit.ref_index in in_span and edit.op in ("sub", "del"):
            score.cs_errors += 1
    # Insertions inside a code-switched region: an engine that invents words in
    # the middle of an English term has damaged that span, and charging the
    # error only to the corpus-wide WER would hide it.
    for start, end in spans:
        mapped: list[int] = [
            h for i in range(start, end) if (h := r2h.get(i)) is not None
        ]
        if len(mapped) < 2:
            continue
        lo, hi = min(mapped), max(mapped)
        expected = hi - lo + 1
        score.cs_errors += max(0, expected - len(mapped))

    # Code-switch boundaries: a Latin/Cyrillic junction in the reference.
    for i in range(len(ref_tokens) - 1):
        left, right = script_of(ref_tokens[i]), script_of(ref_tokens[i + 1])
        if {left, right} != {"latin", "cyrillic"}:
            continue
        score.boundaries += 1
        h_left, h_right = r2h.get(i), r2h.get(i + 1)
        if h_left is None or h_right is None or h_right <= h_left:
            score.boundary_errors += 1
            continue
        if (
            script_of(alignment.hyp[h_left]) != left
            or script_of(alignment.hyp[h_right]) != right
        ):
            score.boundary_errors += 1


def _anchor(r2h: dict[int, int | None], start: int, end: int, hyp_len: int) -> int | None:
    """Nearest hypothesis position for a reference span, searching outward."""
    for i in range(start, end):
        if r2h.get(i) is not None:
            return r2h[i]
    for offset in range(1, max(len(r2h), 1)):
        for probe in (start - offset, end - 1 + offset):
            if r2h.get(probe) is not None:
                return r2h[probe]
    return 0 if hyp_len else None


def _score_terms(
    score: SegmentScore,
    ref: TokenStream,
    hyp: TokenStream,
    r2h: dict[int, int | None],
    glossary: Glossary,
) -> None:
    ref_occurrences = _term_occurrences(ref.terms, glossary)
    hyp_occurrences = _term_occurrences(hyp.terms, glossary)
    score.term_ref_occurrences = len(ref_occurrences)
    score.term_hyp_occurrences = len(hyp_occurrences)

    consumed: set[int] = set()
    for start, end, term, ref_script in ref_occurrences:
        if term.is_name:
            score.name_ref_occurrences += 1
        if ref_script == "latin":
            score.latin_term_occurrences += 1

        anchor = _anchor(r2h, start, end, len(hyp.tokens))
        hit_index = None
        if anchor is not None:
            for idx, (h_start, h_end, h_term, h_script) in enumerate(hyp_occurrences):
                if idx in consumed or h_term.id != term.id:
                    continue
                # Same script class required: a Cyrillic transliteration of a
                # Latin-spoken term is a failure, not a hit (glossary policy).
                if h_script != ref_script:
                    continue
                if h_start <= anchor + TERM_WINDOW and h_end >= anchor - TERM_WINDOW:
                    hit_index = idx
                    break
        if hit_index is not None:
            consumed.add(hit_index)
            score.term_hits += 1
            if term.is_name:
                score.name_hits += 1
            continue

        score.missed_terms.append(term.id)
        width = end - start
        score.misrecognitions.append(
            (term.canonical, _heard_at(hyp, anchor, width, context=1))
        )
        # The substitution verdict reads only the tokens that actually stand
        # where the term was spoken. Widening the window by one for readability
        # would let a neighbouring Russian word turn `Lead House` — a Latin
        # mishearing — into a spurious Latin-to-Cyrillic substitution.
        occupying = _heard_at(hyp, anchor, width, context=0)
        if ref_script == "latin" and occupying and any(
            script_of(t) == "cyrillic" for t in occupying.split()
        ):
            score.latin_to_cyrillic += 1


def _heard_at(hyp: TokenStream, anchor: int | None, width: int, *, context: int) -> str:
    if anchor is None:
        return ""
    lo = max(0, anchor - context)
    hi = min(len(hyp.tokens), anchor + width + context)
    return " ".join(hyp.tokens[lo:hi])


def _score_speakers(
    score: SegmentScore, alignment: Alignment, ref: TokenStream, hyp: TokenStream
) -> None:
    """Accumulate a speaker confusion matrix; the label mapping is global.

    Resolving the mapping per segment would let an engine that shuffles labels
    every minute score as perfect diarisation, so the mapping is solved once
    over the whole corpus in `aggregate`.
    """
    for edit in alignment.edits:
        if edit.op not in ("equal", "sub"):
            continue
        assert edit.ref_index is not None and edit.hyp_index is not None
        ref_speaker = ref.speakers[edit.ref_index]
        hyp_speaker = hyp.speakers[edit.hyp_index]
        if ref_speaker is None or hyp_speaker is None:
            continue
        score.speaker_scored_tokens += 1
        score.speaker_confusion[(ref_speaker, hyp_speaker)] += 1


def _score_timestamps(
    score: SegmentScore, alignment: Alignment, ref: TokenStream, hyp: TokenStream
) -> None:
    for edit in alignment.edits:
        if edit.op != "equal":
            continue
        assert edit.ref_index is not None and edit.hyp_index is not None
        ref_start = ref.starts[edit.ref_index]
        hyp_start = hyp.starts[edit.hyp_index]
        if ref_start is None or hyp_start is None:
            continue
        delta = abs(ref_start - hyp_start)
        score.timestamp_deltas.append(delta)
        if delta <= TIMESTAMP_TOLERANCE_S:
            score.timestamp_within_tolerance += 1


def _ratio(numerator: float, denominator: float) -> float | None:
    """`None`, never zero, when the denominator is empty.

    A metric with no observations is unmeasured. Emitting 0.0 would make an
    engine that was never tested look perfect.
    """
    return numerator / denominator if denominator else None


def _best_speaker_mapping(confusion: Counter) -> int:
    """Agreement under the best hypothesis-to-reference label assignment.

    Greedy on the largest cell, which is exact for the well-separated case and
    never over-credits: it is a lower bound on the optimal assignment.
    """
    remaining = Counter(confusion)
    used_ref: set[str] = set()
    used_hyp: set[str] = set()
    agreement = 0
    while remaining:
        (ref_label, hyp_label), count = max(
            remaining.items(), key=lambda item: (item[1], str(item[0]))
        )
        del remaining[(ref_label, hyp_label)]
        if ref_label in used_ref or hyp_label in used_hyp:
            continue
        used_ref.add(ref_label)
        used_hyp.add(hyp_label)
        agreement += count
    return agreement


def aggregate(scores: Sequence[SegmentScore]) -> dict[str, float | None]:
    """Pool raw counts into corpus-level rates.

    Pooling sums counts and divides once. Averaging per-segment rates would
    weight a ten-second segment like a two-minute one and would not match the
    quantity the bootstrap resamples.
    """
    if not scores:
        return {}
    total = lambda attr: sum(getattr(s, attr) for s in scores)  # noqa: E731

    ref_words = total("ref_words")
    errors = total("substitutions") + total("deletions") + total("insertions")
    term_ref = total("term_ref_occurrences")
    term_hyp = total("term_hyp_occurrences")
    term_hits = total("term_hits")
    precision = _ratio(term_hits, term_hyp)
    recall = _ratio(term_hits, term_ref)
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    elif recall == 0.0:
        # An engine that proposed no glossary term at all, against a reference
        # that contains them, has an F1 of zero. Reporting `None` here would
        # read as "not measured" when the truth is "measured, and it found
        # nothing" -- and it made the JSON disagree with the published table.
        f1 = 0.0
    else:
        f1 = None
    confusion: Counter = Counter()
    for score in scores:
        confusion.update(score.speaker_confusion)
    speaker_tokens = total("speaker_scored_tokens")
    deltas = [d for score in scores for d in score.timestamp_deltas]

    substitutions = total("substitutions")
    deletions = total("deletions")
    return {
        "wer": _ratio(errors, ref_words),
        # Reference-coverage error rate: substitutions and deletions only.
        # Insertions are excluded because an edited reference (fillers and
        # false starts removed by a human editor) charges every engine for
        # words that WERE spoken, which lands entirely in the insertion term.
        # This measures how much of the reference an engine got wrong or
        # missed, which editing does not distort.
        "reference_error_rate": _ratio(substitutions + deletions, ref_words),
        "cer": _ratio(total("char_edits"), total("ref_chars")),
        "cs_wer": _ratio(total("cs_errors"), total("cs_ref_words")),
        "term_precision": precision,
        "term_recall": recall,
        "term_f1": f1,
        "name_recall": _ratio(total("name_hits"), total("name_ref_occurrences")),
        "latin_to_cyrillic_rate": _ratio(
            total("latin_to_cyrillic"), total("latin_term_occurrences")
        ),
        "hallucination_rate": _ratio(total("insertions"), ref_words),
        "omission_rate": _ratio(total("deletions"), ref_words),
        "boundary_error_rate": _ratio(total("boundary_errors"), total("boundaries")),
        "speaker_accuracy": _ratio(_best_speaker_mapping(confusion), speaker_tokens),
        "timestamp_median_abs_error_s": statistics.median(deltas) if deltas else None,
        "timestamp_within_tolerance_rate": _ratio(
            total("timestamp_within_tolerance"), len(deltas)
        ),
        "ref_words": ref_words,
        "segments": len(scores),
    }


#: Metrics where a smaller value is the better result.
LOWER_IS_BETTER = frozenset(
    {
        "wer",
        "reference_error_rate",
        "cer",
        "cs_wer",
        "latin_to_cyrillic_rate",
        "hallucination_rate",
        "omission_rate",
        "boundary_error_rate",
        "timestamp_median_abs_error_s",
    }
)
