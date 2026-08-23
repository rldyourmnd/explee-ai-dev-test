"""Tests for the STT evaluation metrics.

These are written before any engine output exists, and they are the reason the
metric can be trusted: the two failures the employer actually reported —
`РАКа` for RAG and `Lead House` for ClickHouse — are encoded as fixtures and
asserted to score as failures. A metric that scored them as passes would rank
engines on something other than the problem we were asked to solve.

The other cases target the ways a plausible implementation quietly lies: a mean
of per-segment rates presented as a corpus WER, an unmeasured metric emitted as
0.0, a term counted as recognised because the engine happened to say it
somewhere else, a per-segment speaker mapping that flatters a label-shuffling
engine.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness import glossary as glossary_module  # noqa: E402
from harness.align import align  # noqa: E402
from harness.metrics import (  # noqa: E402
    SegmentScore,
    Transcript,
    Word,
    aggregate,
    score_segment,
)
from harness.normalize import normalize_for_wer, normalize_term, script_of, tokens  # noqa: E402


def measured(value: object) -> float:
    """Assert a metric was measured, and narrow it for the type checker.

    `aggregate()` returns `float | None` because an unmeasured metric must never
    be reported as 0.0. A test comparing one has to say it expects a
    measurement, which is what this does.
    """
    assert value is not None, "expected a measured value, got None"
    return float(value)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def glossary():
    return glossary_module.load()


def score(ref: str, hyp: str, glossary, segment_id="s0", engine="e"):
    return score_segment(
        segment_id, engine, Transcript(ref), Transcript(hyp), glossary
    )


# --- the employer's own examples ----------------------------------------------

def test_raka_for_rag_scores_as_a_failure(glossary):
    """`РАКа` instead of RAG: a term miss and a Latin-to-Cyrillic substitution."""
    ref = "мы пересобрали RAG-пайплайн на прошлой неделе"
    hyp = "мы пересобрали РАКа пайплайн на прошлой неделе"
    s = score(ref, hyp, glossary)

    assert s.term_ref_occurrences >= 2  # rag, pipeline
    assert "rag" in s.missed_terms
    assert s.latin_to_cyrillic == 1
    assert s.latin_term_occurrences >= 1
    rates = aggregate([s])
    assert measured(rates["term_recall"]) < 1.0
    assert measured(rates["latin_to_cyrillic_rate"]) > 0
    assert measured(rates["cs_wer"]) > 0


def test_lead_house_for_clickhouse_scores_as_a_failure(glossary):
    """`Lead House` instead of ClickHouse: a name miss that WER alone understates."""
    ref = "перенесли витрину в ClickHouse и стало быстрее"
    hyp = "перенесли витрину в Lead House и стало быстрее"
    s = score(ref, hyp, glossary)

    assert "clickhouse" in s.missed_terms
    assert s.name_ref_occurrences == 1
    assert s.name_hits == 0
    assert aggregate([s])["name_recall"] == 0.0
    # It stays in Latin script, so it is *not* a Cyrillic substitution: the two
    # failure modes are counted separately, which is the point of having both.
    assert s.latin_to_cyrillic == 0


def test_correct_transcription_of_both_terms_passes(glossary):
    ref = "пересобрали RAG-пайплайн и перенесли витрину в ClickHouse"
    s = score(ref, ref, glossary)
    rates = aggregate([s])
    assert rates["wer"] == 0.0
    assert rates["term_recall"] == 1.0
    assert rates["name_recall"] == 1.0
    assert rates["latin_to_cyrillic_rate"] == 0.0
    assert s.missed_terms == []


# --- inflection and normalisation ---------------------------------------------

@pytest.mark.parametrize(
    "ref,hyp",
    [
        ("работаем в ClickHouse", "работаем в ClickHouse-е"),
        ("задеплоили Worker вчера", "задеплоили Workerа вчера"),
        ("подняли Kafka", "подняли Kafkу"),
    ],
)
def test_russian_inflection_on_a_latin_stem_is_still_the_same_term(ref, hyp, glossary):
    """`в ClickHouse-е` is the term, correctly heard — not a miss."""
    s = score(ref, hyp, glossary)
    assert s.missed_terms == []
    assert s.term_hits == s.term_ref_occurrences


@pytest.mark.parametrize(
    "ref,hyp,term_id",
    [
        ("подняли Kafka", "подняли Kafko", "kafka"),
        ("смотрим Grafana", "смотрим Grafano", "grafana"),
        ("живём в Azure", "живём в Azura", "azure"),
        ("перенесли в ClickHouse", "перенесли в ClickHause", "clickhouse"),
    ],
)
def test_a_mangled_product_name_is_never_folded_onto_the_correct_one(
    ref, hyp, term_id, glossary
):
    """The stem fold must not rescue a misheard name.

    An earlier normaliser dropped any final Latin vowel on tokens of five
    characters or more, so `Kafko` and `Kafka` shared a stem and a mangled
    product name scored as a correct one — under the metric whose whole job is
    catching mangled product names.
    """
    s = score(ref, hyp, glossary)
    assert term_id in s.missed_terms
    assert s.term_hits == 0


def test_normalisation_never_rewrites_one_word_into_another():
    """The scoring normaliser must not map `РАКа` onto `rag`."""
    assert normalize_term("РАКа") != "rag"
    assert normalize_for_wer("Lead House") == "lead house"
    assert tokens("RAG-пайплайн") == ["rag", "пайплайн"]
    assert script_of("РАКа") == "cyrillic"
    assert script_of("RAG") == "latin"


def test_case_and_yo_folding_are_not_scored_as_errors(glossary):
    s = score("Ещё раз про Kafka", "еще раз про kafka", glossary)
    assert aggregate([s])["wer"] == 0.0


# --- omission vs hallucination ------------------------------------------------

def test_omission_and_hallucination_are_counted_separately(glossary):
    dropped = score("мы подняли Redis в проде", "мы подняли в проде", glossary)
    assert dropped.deletions == 1 and dropped.insertions == 0
    invented = score(
        "мы подняли Redis", "мы подняли Redis в проде на выходных", glossary
    )
    assert invented.insertions == 4 and invented.deletions == 0

    rates = aggregate([dropped])
    assert measured(rates["omission_rate"]) > 0
    assert rates["hallucination_rate"] == 0.0


def test_empty_hypothesis_is_not_a_free_pass(glossary):
    """Silence must not look good: everything is an omission."""
    s = score("мы подняли Redis в проде", "", glossary)
    rates = aggregate([s])
    assert rates["wer"] == 1.0
    assert rates["omission_rate"] == 1.0
    assert rates["term_recall"] == 0.0
    assert rates["term_precision"] is None  # nothing was proposed


# --- positional honesty -------------------------------------------------------

def test_a_term_said_somewhere_else_does_not_earn_credit(glossary):
    """Recall is positional: the term must appear where it was spoken."""
    ref = "в ClickHouse мы храним события " + "слово " * 30 + "и всё"
    hyp = "в непонятно чём мы храним события " + "слово " * 30 + "и всё ClickHouse"
    s = score(ref, hyp, glossary)
    assert "clickhouse" in s.missed_terms
    assert s.term_hyp_occurrences == 1  # it was proposed, just in the wrong place
    assert aggregate([s])["term_precision"] == 0.0


def test_cyrillic_transliteration_is_not_accepted_for_a_latin_term(glossary):
    s = score("мы используем ClickHouse", "мы используем Кликхаус", glossary)
    assert "clickhouse" in s.missed_terms
    assert s.latin_to_cyrillic == 1


# --- code-switch structure ----------------------------------------------------

def test_code_switch_wer_is_restricted_to_the_english_spans(glossary):
    """Russian filler errors must not move the code-switch metric."""
    ref = "ну вот мы значит подняли Kubernetes кластер"
    hyp = "вот мы подняли Kubernetes кластер"
    s = score(ref, hyp, glossary)
    assert s.cs_ref_words == 1          # `kubernetes`
    assert s.cs_errors == 0             # heard correctly
    assert aggregate([s])["cs_wer"] == 0.0
    assert measured(aggregate([s])["wer"]) > 0.0  # dropped fillers still cost WER


def test_boundary_errors_are_counted_at_script_junctions(glossary):
    clean = score("мы подняли Kafka вчера", "мы подняли Kafka вчера", glossary)
    assert clean.boundaries == 2 and clean.boundary_errors == 0

    broken = score("мы подняли Kafka вчера", "мы подняли кафку вчера", glossary)
    assert broken.boundaries == 2 and broken.boundary_errors == 2
    assert aggregate([broken])["boundary_error_rate"] == 1.0


# --- unmeasured is not zero ---------------------------------------------------

def test_unmeasured_metrics_are_none_not_zero(glossary):
    """An engine that returns no timings must not score as perfectly timed."""
    s = score("всё по-русски без терминов", "всё по-русски без терминов", glossary)
    rates = aggregate(s and [s])
    assert rates["cs_wer"] is None                     # no code-switched span
    assert rates["speaker_accuracy"] is None           # no labels supplied
    assert rates["timestamp_median_abs_error_s"] is None
    assert rates["boundary_error_rate"] is None


def test_aggregate_pools_counts_rather_than_averaging_rates(glossary):
    """A long clean segment must outweigh a short broken one."""
    long_clean = score("а " * 90, "а " * 90, glossary, segment_id="long")
    short_bad = score("б в", "х у", glossary, segment_id="short")
    pooled = aggregate([long_clean, short_bad])
    naive_mean = (0.0 + 1.0) / 2
    assert pooled["wer"] == pytest.approx(2 / 92)
    assert measured(pooled["wer"]) < naive_mean


# --- diarisation and timings --------------------------------------------------

def _spoken(pairs, speaker_of=None):
    return Transcript.from_words(
        [
            Word(text=t, start=float(i), end=float(i) + 0.5,
                 speaker=(speaker_of(i) if speaker_of else s))
            for i, (t, s) in enumerate(pairs)
        ]
    )


def test_speaker_mapping_is_global_not_per_segment(glossary):
    """An engine that renames speakers every segment must not score as perfect."""
    words = [("раз", "A"), ("два", "A"), ("три", "B"), ("четыре", "B")]
    ref = _spoken(words)
    consistent = _spoken([(t, {"A": "spk_0", "B": "spk_1"}[s]) for t, s in words])
    flipped = _spoken([(t, {"A": "spk_1", "B": "spk_0"}[s]) for t, s in words])

    good = [
        score_segment("s0", "e", ref, consistent, glossary),
        score_segment("s1", "e", ref, consistent, glossary),
    ]
    shuffler = [
        score_segment("s0", "e", ref, consistent, glossary),
        score_segment("s1", "e", ref, flipped, glossary),
    ]
    assert aggregate(good)["speaker_accuracy"] == 1.0
    assert aggregate(shuffler)["speaker_accuracy"] == 0.5


def test_timestamp_error_is_measured_against_the_reference(glossary):
    words = [("раз", "A"), ("два", "A")]
    ref = _spoken(words)
    shifted = Transcript.from_words(
        [Word(text=t, start=float(i) + 0.2, end=float(i) + 0.7, speaker=s)
         for i, (t, s) in enumerate(words)]
    )
    rates = aggregate([score_segment("s0", "e", ref, shifted, glossary)])
    assert rates["timestamp_median_abs_error_s"] == pytest.approx(0.2)
    assert rates["timestamp_within_tolerance_rate"] == 1.0

    late = Transcript.from_words(
        [Word(text=t, start=float(i) + 3.0, end=float(i) + 3.5, speaker=s)
         for i, (t, s) in enumerate(words)]
    )
    late_rates = aggregate([score_segment("s0", "e", ref, late, glossary)])
    assert late_rates["timestamp_within_tolerance_rate"] == 0.0


# --- alignment ----------------------------------------------------------------

def test_alignment_is_deterministic_and_minimal():
    a = align(["a", "b", "c"], ["a", "x", "c"])
    assert (a.hits, a.substitutions, a.deletions, a.insertions) == (2, 1, 0, 0)
    assert a.ref_to_hyp() == {0: 0, 1: 1, 2: 2}
    again = align(["a", "b", "c"], ["a", "x", "c"])
    assert a.edits == again.edits


def test_glossary_is_loadable_and_fingerprinted(glossary):
    assert len(glossary) >= 40
    assert len(glossary.fingerprint) == 64
    assert glossary.by_id("clickhouse").is_name
    assert not glossary.by_id("rag").is_name
    # No accepted form may be a Cyrillic transliteration of ClickHouse.
    assert all(
        script_of(" ".join(v)) == "latin" for v in glossary.by_id("clickhouse").variants
    )


def test_latin_stemming_does_not_collide_two_glossary_terms(glossary):
    """The stem fold must not silently merge two distinct terms."""
    owners: dict[tuple[str, ...], set[str]] = {}
    for term in glossary:
        for variant in term.variants:
            owners.setdefault(variant, set()).add(term.id)
    collisions = {v: ids for v, ids in owners.items() if len(ids) > 1}
    assert collisions == {}


def test_segment_score_starts_empty():
    s = SegmentScore(segment_id="s", engine="e")
    assert aggregate([s])["wer"] is None
