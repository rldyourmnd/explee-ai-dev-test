"""Tests for the gold-reference build.

The reference is the metric, so the properties tested here are the ones that
decide whether the whole benchmark means anything: a reference derived from an
engine under test is refused, an unadjudicated disagreement is excluded rather
than silently resolved, and inter-annotator agreement is measured in the same
units the engines are judged in.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness import glossary as glossary_module  # noqa: E402
from harness.metrics import Word  # noqa: E402
from harness.reference import (  # noqa: E402
    UNINTELLIGIBLE,
    Adjudication,
    Annotation,
    DraftOrigin,
    build,
    corpus_agreement,
    has_cyrillic_transliteration,
    inter_annotator,
    load_pass,
    save_pass,
    validate,
    validate_draft_origin,
)


@pytest.fixture(scope="module")
def glossary():
    return glossary_module.load()


def words(text, speaker="S1"):
    return [Word(text=t, speaker=speaker) for t in text.split()]


def ann(segment_id, annotator, text, speaker="S1", **kwargs):
    return Annotation(
        segment_id=segment_id, annotator=annotator,
        words=words(text, speaker), **kwargs
    )


# --- circularity --------------------------------------------------------------

def test_a_draft_from_an_engine_under_test_is_refused():
    """Scoring an engine against a reference built from it measures agreement."""
    draft = DraftOrigin(kind="engine", engine="deepgram", excluded_from_ranking=False)
    problems = validate_draft_origin(draft)
    assert problems and problems[0].rule == "production-step-1"


def test_a_draft_from_an_excluded_engine_is_allowed_but_recorded():
    draft = DraftOrigin(
        kind="engine", engine="some-engine", excluded_from_ranking=True,
        note="excluded from the ranking; residual bias disclosed in the report",
    )
    assert validate_draft_origin(draft) == []
    a = ann("s0", "ann1", "мы подняли ClickHouse", draft=draft)
    result = build([a], [ann("s0", "ann2", "мы подняли ClickHouse")])
    assert any(o.kind == "engine" for o in result.draft_origins)


# --- policy validation --------------------------------------------------------

def test_speaker_labels_must_be_stable_ids(glossary):
    bad = Annotation("s0", "ann1", words=[Word(text="привет", speaker="speaker_0")])
    assert any(v.rule == "R10" for v in validate(bad, glossary))
    good = ann("s0", "ann1", "привет", speaker="S2")
    assert not any(v.rule == "R10" for v in validate(good, glossary))


def test_a_segment_too_unintelligible_is_excluded_not_guessed(glossary):
    text = " ".join([UNINTELLIGIBLE] * 3 + ["слово"] * 7)
    bad = ann("s0", "ann1", text)
    assert bad.unintelligible_share() == pytest.approx(0.3)
    assert any(v.rule == "R9" for v in validate(bad, glossary))

    result = build([bad], [ann("s0", "ann2", text)])
    assert "s0" in result.excluded
    assert result.reference == {}


def test_a_few_unintelligible_words_are_kept(glossary):
    text = " ".join([UNINTELLIGIBLE] + ["слово"] * 19)
    ok = ann("s0", "ann1", text)
    assert not any(v.rule == "R9" for v in validate(ok, glossary))


def test_numerals_written_as_words_are_flagged(glossary):
    assert any(v.rule == "R5" for v in validate(ann("s0", "a", "около триста мс"), glossary))
    assert not any(v.rule == "R5" for v in validate(ann("s0", "a", "около 300 мс"), glossary))


def test_a_spelled_out_abbreviation_is_flagged(glossary):
    assert any(v.rule == "R6" for v in validate(ann("s0", "a", "открыли а п и вчера"), glossary))
    assert not any(v.rule == "R6" for v in validate(ann("s0", "a", "открыли API вчера"), glossary))


def test_cyrillic_transliteration_is_flagged_for_the_annotator(glossary):
    flagged = has_cyrillic_transliteration("перенесли в Кликхаус", glossary)
    assert any("ClickHouse" in f for f in flagged)
    assert has_cyrillic_transliteration("перенесли в ClickHouse", glossary) == []


# --- agreement ----------------------------------------------------------------

def test_identical_passes_agree_perfectly():
    a = ann("s0", "ann1", "мы подняли ClickHouse вчера")
    b = ann("s0", "ann2", "мы подняли ClickHouse вчера")
    assert inter_annotator(a, b).wer == 0.0


def test_agreement_is_pooled_over_counts_not_averaged():
    long_pair = (ann("s0", "a", " ".join(["слово"] * 90)),
                 ann("s0", "b", " ".join(["слово"] * 90)))
    short_pair = (ann("s1", "a", "раз два"), ann("s1", "b", "три четыре"))
    pooled = corpus_agreement([long_pair, short_pair])
    assert pooled == pytest.approx(2 / 92)
    assert pooled < 0.5  # the naive mean of 0.0 and 1.0


def test_agreement_across_different_segments_is_refused():
    with pytest.raises(ValueError):
        inter_annotator(ann("s0", "a", "раз"), ann("s1", "b", "раз"))


# --- build --------------------------------------------------------------------

def test_agreed_segments_need_no_adjudication():
    result = build(
        [ann("s0", "ann1", "мы подняли ClickHouse")],
        [ann("s0", "ann2", "мы подняли ClickHouse")],
    )
    assert result.coverage() == 1
    assert result.excluded == {}
    assert result.agreement_wer == 0.0


def test_an_unadjudicated_disagreement_is_excluded_not_silently_resolved():
    result = build(
        [ann("s0", "ann1", "мы подняли ClickHouse")],
        [ann("s0", "ann2", "мы подняли Kafka")],
    )
    assert result.reference == {}
    assert "no adjudication" in result.excluded["s0"]


def test_adjudication_resolves_a_disagreement_and_records_its_rule():
    result = build(
        [ann("s0", "ann1", "перенесли в ClickHouse")],
        [ann("s0", "ann2", "перенесли в Кликхаус")],
        [Adjudication("s0", chosen="ann1", rule="R1",
                      note="Latin script for a Latin-script term")],
    )
    assert result.coverage() == 1
    assert "ClickHouse" in result.reference["s0"].text


def test_adjudication_may_supply_its_own_merged_text():
    merged = words("перенесли витрину в ClickHouse")
    result = build(
        [ann("s0", "ann1", "перенесли в ClickHouse")],
        [ann("s0", "ann2", "перенесли витрину в Кликхаус")],
        [Adjudication("s0", chosen="merged", rule="R1", words=merged)],
    )
    assert result.reference["s0"].text == "перенесли витрину в ClickHouse"


def test_a_segment_only_one_annotator_covered_is_excluded():
    result = build([ann("s0", "ann1", "раз два")], [])
    assert "only one annotator" in result.excluded["s0"]


def test_build_reports_agreement_and_annotators():
    result = build(
        [ann("s0", "ann1", "раз два три"), ann("s1", "ann1", "четыре пять")],
        [ann("s0", "ann2", "раз два три"), ann("s1", "ann2", "четыре шесть")],
        [Adjudication("s1", chosen="ann1", rule="R7")],
    )
    assert result.annotators == ("ann1", "ann2")
    assert result.coverage() == 2
    assert result.agreement_wer == pytest.approx(1 / 5)


# --- round trip ---------------------------------------------------------------

def test_annotation_pass_round_trips(tmp_path):
    original = [
        Annotation("s0", "ann1",
                   words=[Word(text="мы", start=0.0, end=0.3, speaker="S1"),
                          Word(text="ClickHouse", start=0.3, end=1.1, speaker="S1")],
                   notes="clean audio")
    ]
    path = save_pass(tmp_path / "pass1.json", original)
    reloaded = load_pass(path)
    assert reloaded[0].words[1].text == "ClickHouse"
    assert reloaded[0].words[1].start == 0.3
    assert reloaded[0].notes == "clean audio"
    assert reloaded[0].transcript.has_speakers
