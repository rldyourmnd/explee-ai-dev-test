"""Building the gold reference under the published policy.

The reference is the metric. Everything else in this benchmark is arithmetic on
top of it, so this module exists to make the annotation pass fast, checkable and
hard to do sloppily — not to produce a reference automatically.

It enforces the mechanically checkable parts of `docs/reference-policy.md`
(speaker-label stability, unintelligible-span accounting, the exclusion
threshold, spelled-out abbreviations, numerals as digits), measures
inter-annotator agreement with the same metric code the engines are scored
with, and carries an adjudication pass whose every decision records the rule it
applied.

What it deliberately does **not** do is invent transcript text. A reference
drafted from an engine's output is biased toward that engine, and the policy
forbids it (production step 1). Where a draft is unavoidable, `DraftOrigin`
records where it came from so the report can state the residual bias instead of
hiding it.

Stdlib only.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .align import align
from .glossary import Glossary
from .metrics import Transcript, Word
from .normalize import CYRILLIC, tokens

UNINTELLIGIBLE = "[unintelligible]"

#: Policy R9: a segment this badly degraded is excluded from the corpus rather
#: than guessed at, and the exclusion is published with its count.
MAX_UNINTELLIGIBLE_SHARE = 0.10

SPEAKER_LABEL = re.compile(r"^S[1-9][0-9]*$")

#: Policy R5: numerals are digits. Catching every Russian numeral is a research
#: problem; catching the common ones is enough to stop a pass drifting.
_NUMBER_WORDS = {
    "ноль", "один", "одна", "два", "две", "три", "четыре", "пять", "шесть",
    "семь", "восемь", "девять", "десять", "одиннадцать", "двенадцать",
    "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
    "восемьдесят", "девяносто", "сто", "двести", "триста", "тысяча", "тысяч",
    "миллион", "миллионов", "миллисекунд", "трёхсот", "трехсот",
}
_UNITS_OK = {"миллисекунд", "миллионов", "тысяч"}


@dataclass(frozen=True)
class Violation:
    rule: str
    segment_id: str
    detail: str


@dataclass
class DraftOrigin:
    """Where a pre-filled draft came from, if one was used at all.

    `engine` naming a system under test is a bias the report must disclose;
    `validate_draft_origin` refuses that combination outright.
    """

    kind: str = "none"  # none | engine | prior-human
    engine: str = ""
    excluded_from_ranking: bool = False
    note: str = ""


@dataclass
class Annotation:
    """One annotator's pass over one segment."""

    segment_id: str
    annotator: str
    words: list[Word] = field(default_factory=list)
    notes: str = ""
    draft: DraftOrigin = field(default_factory=DraftOrigin)

    @property
    def transcript(self) -> Transcript:
        return Transcript.from_words(self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def unintelligible_share(self) -> float:
        total = len(self.words)
        if not total:
            return 0.0
        return sum(1 for w in self.words if w.text.strip() == UNINTELLIGIBLE) / total


def validate_draft_origin(draft: DraftOrigin) -> list[Violation]:
    """A reference drafted from an engine under test is circular. Refuse it."""
    if draft.kind == "engine" and not draft.excluded_from_ranking:
        return [
            Violation(
                "production-step-1",
                "",
                f"draft came from {draft.engine or 'an engine'}, which is still in "
                "the ranking: scoring an engine against a reference derived from "
                "itself measures agreement, not accuracy",
            )
        ]
    return []


def validate(annotation: Annotation, glossary: Glossary | None = None) -> list[Violation]:
    """Mechanically checkable policy rules. Not a substitute for adjudication."""
    problems: list[Violation] = []
    seg = annotation.segment_id

    for word in annotation.words:
        if word.speaker is None or not SPEAKER_LABEL.match(word.speaker):
            problems.append(
                Violation("R10", seg, f"speaker label {word.speaker!r} is not S1, S2, …")
            )
            break

    if annotation.unintelligible_share() > MAX_UNINTELLIGIBLE_SHARE:
        problems.append(
            Violation(
                "R9", seg,
                f"{annotation.unintelligible_share():.0%} unintelligible exceeds "
                f"{MAX_UNINTELLIGIBLE_SHARE:.0%}; exclude the segment rather than guess",
            )
        )

    for token in tokens(annotation.text):
        if token in _NUMBER_WORDS and token not in _UNITS_OK:
            problems.append(
                Violation("R5", seg, f"numeral written as a word: {token!r}")
            )
            break

    # R6: letter-by-letter spelling of an abbreviation, e.g. `а п и`.
    single_letters = 0
    for token in tokens(annotation.text):
        single_letters = single_letters + 1 if len(token) == 1 and token.isalpha() else 0
        if single_letters >= 3:
            problems.append(
                Violation("R6", seg, "three consecutive single letters: an "
                                     "abbreviation spelled out rather than written")
            )
            break

    problems.extend(validate_draft_origin(annotation.draft))
    return problems


@dataclass
class Agreement:
    """Inter-annotator agreement, in the units the engines are judged in."""

    segment_id: str
    wer: float | None
    ref_words: int
    disagreements: int

    @property
    def clean(self) -> bool:
        return self.wer == 0.0


def inter_annotator(first: Annotation, second: Annotation) -> Agreement:
    """WER between two independent passes over the same segment.

    Published, because it bounds the whole exercise: engines closer together
    than the reference's own uncertainty cannot be separated by it, and the
    report has to say so rather than rank them anyway.
    """
    if first.segment_id != second.segment_id:
        raise ValueError("agreement is per segment; ids differ")
    a, b = tokens(first.text), tokens(second.text)
    alignment = align(a, b)
    errors = alignment.substitutions + alignment.deletions + alignment.insertions
    return Agreement(
        segment_id=first.segment_id,
        wer=(errors / len(a)) if a else None,
        ref_words=len(a),
        disagreements=errors,
    )


def corpus_agreement(pairs: Iterable[tuple[Annotation, Annotation]]) -> float | None:
    """Pooled inter-annotator WER over the corpus. Counts, not a mean of rates."""
    errors = 0
    words = 0
    for first, second in pairs:
        result = inter_annotator(first, second)
        if result.wer is None:
            continue
        errors += result.disagreements
        words += result.ref_words
    return errors / words if words else None


@dataclass
class Adjudication:
    """A third-pass decision, recording the rule it applied."""

    segment_id: str
    chosen: str  # annotator name, or "merged"
    rule: str
    words: list[Word] = field(default_factory=list)
    note: str = ""


@dataclass
class ReferenceBuild:
    reference: dict[str, Transcript]
    excluded: dict[str, str]
    agreement_wer: float | None
    violations: list[Violation]
    annotators: tuple[str, ...]
    draft_origins: tuple[DraftOrigin, ...] = ()

    def coverage(self) -> int:
        return len(self.reference)


def build(
    first_pass: Sequence[Annotation],
    second_pass: Sequence[Annotation],
    adjudications: Sequence[Adjudication] = (),
    glossary: Glossary | None = None,
) -> ReferenceBuild:
    """Combine two independent passes plus adjudication into the reference.

    Segments the two passes agree on verbatim need no adjudication. Segments
    they disagree on require one, and are **excluded** if none was supplied —
    silently picking one annotator would be a decision nobody recorded.
    """
    by_id_first = {a.segment_id: a for a in first_pass}
    by_id_second = {a.segment_id: a for a in second_pass}
    decisions = {d.segment_id: d for d in adjudications}

    reference: dict[str, Transcript] = {}
    excluded: dict[str, str] = {}
    violations: list[Violation] = []
    paired: list[tuple[Annotation, Annotation]] = []

    for segment_id in sorted(set(by_id_first) | set(by_id_second)):
        a, b = by_id_first.get(segment_id), by_id_second.get(segment_id)
        if a is None or b is None:
            excluded[segment_id] = "only one annotator covered this segment"
            continue
        problems = validate(a, glossary) + validate(b, glossary)
        violations.extend(problems)
        if any(p.rule == "R9" for p in problems):
            excluded[segment_id] = "unintelligible share above the policy threshold"
            continue
        paired.append((a, b))

        if tokens(a.text) == tokens(b.text):
            reference[segment_id] = a.transcript
            continue
        decision = decisions.get(segment_id)
        if decision is None:
            excluded[segment_id] = "annotators disagreed and no adjudication was recorded"
            continue
        if decision.words:
            reference[segment_id] = Transcript.from_words(decision.words)
        elif decision.chosen == a.annotator:
            reference[segment_id] = a.transcript
        elif decision.chosen == b.annotator:
            reference[segment_id] = b.transcript
        else:
            excluded[segment_id] = f"adjudication named unknown annotator {decision.chosen!r}"

    origins = tuple(
        {(x.kind, x.engine): x for x in
         [a.draft for a in first_pass] + [b.draft for b in second_pass]}.values()
    )
    return ReferenceBuild(
        reference=reference,
        excluded=excluded,
        agreement_wer=corpus_agreement(paired),
        violations=violations,
        annotators=tuple(sorted({a.annotator for a in [*first_pass, *second_pass]})),
        draft_origins=origins,
    )


#: Seed for the from-scratch slice. Fixed here, in the same commit that
#: declares the rule, so the slice cannot be reselected after someone has seen
#: which segments are easy.
SCRATCH_SLICE_SEED = 20260823
SCRATCH_SLICE_SIZE = 6


def select_scratch_slice(
    segment_ids: Sequence[str],
    size: int = SCRATCH_SLICE_SIZE,
    seed: int = SCRATCH_SLICE_SEED,
) -> list[str]:
    """Pick the segments one annotator transcribes from scratch, unaided.

    These segments measure the residual bias of the draft-assisted reference:
    errors that both drafting engines made, and that a correcting annotator
    therefore never saw, show up as the difference between the unaided
    transcript and the draft-corrected one on exactly these segments.

    The rule is declared and seeded before anyone listens. Deterministic from
    the segment ids alone, so anybody can recompute the selection and confirm
    it was not chosen after the fact.
    """
    import random

    ordered = sorted(segment_ids)
    if size >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, size))


@dataclass
class ResidualBias:
    """How much the draft-assisted reference missed, measured not asserted."""

    segments: tuple[str, ...]
    unaided_words: int
    missed_errors: int

    @property
    def rate(self) -> float | None:
        return self.missed_errors / self.unaided_words if self.unaided_words else None

    def sentence(self) -> str:
        if self.rate is None:
            return "residual bias not measurable: the from-scratch slice is empty."
        return (
            f"On {len(self.segments)} segments transcribed from scratch, the "
            f"draft-assisted reference differed from the unaided one in "
            f"{self.missed_errors} of {self.unaided_words} words "
            f"({self.rate:.2%}). Treat that as the floor on this benchmark's "
            f"resolution: engine differences smaller than it are not separable."
        )


def measure_residual_bias(
    unaided: Sequence[Annotation],
    draft_assisted: dict[str, Transcript],
) -> ResidualBias:
    """Compare unaided transcripts against the draft-assisted reference.

    Every disagreement is counted against the draft-assisted reference. That is
    deliberately unflattering: some disagreements will be annotator slips
    rather than draft contamination, so the number is an upper bound on the
    reference's own error, and an upper bound is the safe direction here.
    """
    missed = 0
    words = 0
    covered: list[str] = []
    for annotation in unaided:
        reference = draft_assisted.get(annotation.segment_id)
        if reference is None:
            continue
        covered.append(annotation.segment_id)
        truth = tokens(annotation.text)
        alignment = align(truth, tokens(reference.text))
        words += len(truth)
        missed += (
            alignment.substitutions + alignment.deletions + alignment.insertions
        )
    return ResidualBias(tuple(sorted(covered)), words, missed)


@dataclass
class DisagreementSpan:
    """Where two drafting engines disagree — the spans worth a human's time."""

    segment_id: str
    density: float
    disputed_words: int
    total_words: int


def disagreement_spans(
    draft_a: dict[str, Transcript], draft_b: dict[str, Transcript]
) -> list[DisagreementSpan]:
    """Rank segments by how much the two drafts disagree, densest first.

    Errors concentrate where independent engines diverge, so this is where an
    annotator's attention buys the most reference quality per minute. Segments
    the drafts agree on are not skipped — they are simply annotated later, and
    the from-scratch slice measures what agreeing on a shared error costs.
    """
    spans: list[DisagreementSpan] = []
    for segment_id in sorted(set(draft_a) & set(draft_b)):
        a, b = tokens(draft_a[segment_id].text), tokens(draft_b[segment_id].text)
        if not a and not b:
            continue
        alignment = align(a, b)
        disputed = (
            alignment.substitutions + alignment.deletions + alignment.insertions
        )
        total = max(len(a), 1)
        spans.append(
            DisagreementSpan(segment_id, disputed / total, disputed, len(a))
        )
    spans.sort(key=lambda s: (-s.density, s.segment_id))
    return spans


def _word_to_json(word: Word) -> dict:
    return {"text": word.text, "start": word.start, "end": word.end,
            "speaker": word.speaker}


def save_pass(path: Path | str, annotations: Sequence[Annotation]) -> Path:
    payload = [
        {
            "segment_id": a.segment_id,
            "annotator": a.annotator,
            "notes": a.notes,
            "draft": asdict(a.draft),
            "words": [_word_to_json(w) for w in a.words],
        }
        for a in annotations
    ]
    path = Path(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_pass(path: Path | str) -> list[Annotation]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Annotation(
            segment_id=entry["segment_id"],
            annotator=entry["annotator"],
            words=[Word(**w) for w in entry["words"]],
            notes=entry.get("notes", ""),
            draft=DraftOrigin(**entry.get("draft", {})),
        )
        for entry in data
    ]


def has_cyrillic_transliteration(text: str, glossary: Glossary) -> list[str]:
    """Flag Cyrillic tokens that look like a Latin glossary term (policy R1).

    Advisory only: it cannot know what was said. It exists so an annotator who
    typed `Кликхаус` out of habit sees the rule before adjudication does.
    """
    flagged: list[str] = []
    latin_terms = [
        t for t in glossary
        if t.script == "latin" and all(not CYRILLIC.search(" ".join(v)) for v in t.variants)
    ]
    for token in tokens(text):
        if not CYRILLIC.search(token) or len(token) < 5:
            continue
        for term in latin_terms:
            if _looks_transliterated(token, term.canonical):
                flagged.append(f"{token} -> {term.canonical}?")
                break
    return flagged


#: Latin spellings and Cyrillic transliterations disagree on which letter makes
#: the /k/ sound, so both sides are folded before comparison: `Кликхаус`
#: transliterates to `klikhaus` while `ClickHouse` folds to `klikkhouse`.
_LATIN_FOLD = str.maketrans({"c": "k", "q": "k", "y": "i", "j": "i"})
_HEAD = 6
_MAX_HEAD_DISTANCE = 2


_TRANSLIT = str.maketrans({
    "к": "k", "л": "l", "и": "i", "х": "h", "а": "a", "у": "u",
    "с": "s", "е": "e", "р": "r", "о": "o", "п": "p", "т": "t", "н": "n",
    "м": "m", "д": "d", "г": "g", "б": "b", "в": "v", "ф": "f", "з": "z",
    "я": "a", "ю": "u", "й": "i", "ы": "y", "э": "e",
})


def _looks_transliterated(token: str, canonical: str) -> bool:
    """Fuzzy prefix match between a Cyrillic token and a Latin term.

    Advisory: two edits of slack on a six-character head catches `Кликхаус` for
    `ClickHouse` without needing a transliteration table that is right about
    every Russian speaker's spelling habits.
    """
    head = token.translate(_TRANSLIT)[:_HEAD]
    target = canonical.casefold().translate(_LATIN_FOLD)[:_HEAD]
    if not head or not target:
        return False
    alignment = align(list(head), list(target))
    distance = (
        alignment.substitutions + alignment.deletions + alignment.insertions
    )
    return distance <= _MAX_HEAD_DISTANCE
