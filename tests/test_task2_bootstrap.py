"""Tests for paired bootstrap intervals and the pre-declared decision rule.

The property that matters here is restraint: on a one-hour corpus two good
engines will often be indistinguishable, and the harness must say so rather
than promote a point estimate into a ranking. So the tests assert both
directions — a real difference is detected, and a coin-flip difference is
*not* declared a winner.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness.bootstrap import (  # noqa: E402
    bootstrap_interval,
    decide,
    paired_bootstrap,
    rank,
)
from harness.metrics import SegmentScore  # noqa: E402

RESAMPLES = 400  # enough to exercise the code path; the run uses 10 000


def segments(engine, error_counts, ref_words=20):
    return [
        SegmentScore(
            segment_id=f"s{i}",
            engine=engine,
            ref_words=ref_words,
            substitutions=errors,
            hits=ref_words - errors,
        )
        for i, errors in enumerate(error_counts)
    ]


def test_a_large_consistent_difference_is_detected():
    good = segments("good", [0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
    bad = segments("bad", [8, 9, 8, 9, 8, 9, 8, 9, 8, 9])
    comparison = paired_bootstrap("wer", good, bad, resamples=RESAMPLES)
    assert comparison.better == "good"
    assert not comparison.indistinguishable
    assert comparison.difference.low > 0  # bad has the higher WER


def test_a_tiny_difference_is_reported_as_no_winner():
    a = segments("a", [2, 3, 2, 3, 2, 3, 2, 3, 2, 3])
    b = segments("b", [3, 2, 3, 2, 3, 2, 3, 2, 3, 2])
    comparison = paired_bootstrap("wer", a, b, resamples=RESAMPLES)
    assert comparison.indistinguishable
    assert comparison.better is None
    assert "do not establish a winner" in comparison.sentence()


def test_pairing_is_enforced():
    a = segments("a", [1, 1, 1])
    b = segments("b", [1, 1])
    with pytest.raises(ValueError):
        paired_bootstrap("wer", a, b, resamples=RESAMPLES)


def test_interval_is_seeded_and_reproducible():
    scores = segments("a", [1, 4, 0, 7, 2, 3, 5, 1, 0, 2])
    first = bootstrap_interval("wer", scores, resamples=RESAMPLES, seed=7)
    second = bootstrap_interval("wer", scores, resamples=RESAMPLES, seed=7)
    assert (first.low, first.point, first.high) == (second.low, second.point, second.high)
    assert first.low <= first.point <= first.high


def test_unmeasurable_metric_yields_no_interval_and_no_winner():
    a = segments("a", [1, 1, 1])
    b = segments("b", [2, 2, 2])
    comparison = paired_bootstrap("cs_wer", a, b, resamples=RESAMPLES)
    assert not comparison.difference.measured
    assert comparison.better is None
    assert "not measurable" in comparison.sentence()


def test_rank_orders_lower_wer_first():
    engines = {
        "a": segments("a", [5, 5, 5, 5]),
        "b": segments("b", [1, 1, 1, 1]),
        "c": segments("c", [9, 9, 9, 9]),
    }
    ordered = [name for name, _ in rank(engines, "wer", resamples=RESAMPLES)]
    assert ordered == ["b", "a", "c"]


def test_decision_rule_rejects_an_engine_that_fails_the_guardrail():
    engines = {
        "clean": segments("clean", [1] * 8),
        "unusable": segments("unusable", [14] * 8),
    }
    outcome = decide(
        engines, primary="wer", guardrail_metric="wer", guardrail_max=0.35,
        resamples=RESAMPLES,
    )
    assert outcome["winner"] == "clean"
    assert "unusable" in outcome["rejected"]


def test_decision_rule_breaks_a_statistical_tie_on_cost():
    engines = {
        "pricey": segments("pricey", [2, 3, 2, 3, 2, 3, 2, 3]),
        "cheap": segments("cheap", [3, 2, 3, 2, 3, 2, 3, 2]),
    }
    outcome = decide(
        engines, primary="wer", guardrail_metric="wer", guardrail_max=0.5,
        cost_usd={"pricey": 4.10, "cheap": 0.90}, resamples=RESAMPLES,
    )
    assert set(outcome["indistinguishable_from_leader"]) == {"pricey", "cheap"}
    assert outcome["winner"] == "cheap"
    assert "cheapest" in outcome["basis"]


def test_no_engine_meeting_the_guardrail_is_reported_not_papered_over():
    engines = {"a": segments("a", [15] * 5), "b": segments("b", [16] * 5)}
    outcome = decide(
        engines, primary="wer", guardrail_metric="wer", guardrail_max=0.30,
        resamples=RESAMPLES,
    )
    assert outcome["winner"] is None
    assert outcome["reason"] == "no engine met the guardrail"
