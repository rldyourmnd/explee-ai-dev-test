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
