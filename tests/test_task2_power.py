"""Tests for the power simulation and the coverage eligibility policy."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness.metrics import SegmentScore  # noqa: E402
from harness.power import simulate  # noqa: E402
from harness.runner import MIN_COVERAGE, eligibility  # noqa: E402


def template(units=99, terms_per_unit=1, ref_words=50):
    return [
        SegmentScore(segment_id=f"blk-{i:04d}", engine="template",
                     ref_words=ref_words, hits=ref_words,
                     term_ref_occurrences=terms_per_unit,
                     term_hyp_occurrences=terms_per_unit)
        for i in range(units)
    ]


def test_a_large_difference_is_detected_more_often_than_a_small_one():
    results = simulate(
        template(terms_per_unit=2), corpus_seconds=2952.821,
        deltas=(0.03, 0.25), trials=25, resamples=200,
    )
    small, large = results[0], results[1]
    assert large.power > small.power
    assert 0.0 <= small.power <= 1.0


def test_power_result_reports_itself_honestly():
    results = simulate(
        template(), corpus_seconds=2952.821, deltas=(0.05,),
        trials=10, resamples=150,
    )
    sentence = results[0].sentence()
    assert "term_f1" in sentence and "detected" in sentence
    assert results[0].sign_errors <= results[0].detections


def test_detection_never_points_the_wrong_way_for_a_huge_gap():
    results = simulate(
        template(terms_per_unit=3), corpus_seconds=2952.821,
        deltas=(0.35,), trials=15, resamples=200,
    )
    assert results[0].sign_errors == 0


# --- coverage policy ----------------------------------------------------------

def scores_for(engine, n):
    return [SegmentScore(segment_id=f"blk-{i:04d}", engine=engine) for i in range(n)]


def test_coverage_floor_is_98_percent_and_labelled_as_policy():
    assert MIN_COVERAGE == 0.98
    status = eligibility({"flaky": scores_for("flaky", 95)}, corpus_size=99)
    assert status["flaky"]["rankable"] is False
    policy = status["flaky"]["policy"]
    # eligibility() returns dict[str, object]; assert the type rather than
    # assuming it, since the whole point of this gate is catching that.
    assert isinstance(policy, str)
    assert "operational policy" in policy


def test_two_failed_segments_in_a_hundred_is_still_rankable():
    status = eligibility({"solid": scores_for("solid", 98)}, corpus_size=100)
    assert status["solid"]["rankable"] is True
    assert status["solid"]["coverage"] == pytest.approx(0.98)


def test_a_complete_engine_has_full_coverage():
    status = eligibility({"complete": scores_for("complete", 99)}, corpus_size=99)
    assert status["complete"]["coverage"] == 1.0
    assert status["complete"]["rankable"] is True


# --- coverage measured from raw files, not from scored blocks -----------------

def test_a_missing_segment_is_invisible_to_block_scores_but_caught_by_raw_coverage():
    """The defect this closes: scored units cannot detect a dropped segment.

    The document scorer emits one score per reference block regardless of what
    the engine returned, so an engine that dropped a quarter of the audio still
    yields a full-length score list and a flattering average over what it did
    manage. Only counting raw returned files against the manifest sees it.
    """
    from harness.runner import raw_coverage

    manifest_ids = [f"seg-{i:04d}" for i in range(99)]
    complete = manifest_ids
    dropped = manifest_ids[:70]          # returned 70 of 99

    # Scored blocks look identical for both: 99 units either way.
    scored_complete = scores_for("complete", 99)
    scored_dropped = scores_for("dropped", 99)
    assert len(scored_complete) == len(scored_dropped)
    assert eligibility({"dropped": scored_dropped}, corpus_size=99)["dropped"]["rankable"] is True

    status = raw_coverage({"complete": complete, "dropped": dropped}, manifest_ids)
    assert status["complete"]["rankable"] is True
    assert status["complete"]["coverage"] == 1.0
    assert status["dropped"]["rankable"] is False
    assert status["dropped"]["segments_missing"] == 29


def test_raw_coverage_ignores_ids_not_in_the_manifest():
    from harness.runner import raw_coverage
    manifest_ids = ["seg-0000", "seg-0001"]
    status = raw_coverage({"e": ["seg-0000", "seg-0001", "seg-9999"]}, manifest_ids)
    assert status["e"]["segments_returned"] == 2
    assert status["e"]["coverage"] == 1.0
