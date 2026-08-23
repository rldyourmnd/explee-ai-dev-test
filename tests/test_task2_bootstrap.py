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


# --- the declared tie-break order ---------------------------------------------

def rich(engine, wer_errors, cs_errors, ref_words=20, cs_words=5):
    """Segments with independently controllable overall and code-switch error."""
    return [
        SegmentScore(
            segment_id=f"s{i}", engine=engine, ref_words=ref_words,
            substitutions=w, hits=ref_words - w,
            cs_ref_words=cs_words, cs_errors=c,
        )
        for i, (w, c) in enumerate(zip(wer_errors, cs_errors))
    ]


def test_a_tie_on_the_primary_metric_goes_to_code_switch_wer_not_cost():
    """Cost is step 4 of the frozen rule, not step 1."""
    n = 10
    a = rich("a", [2, 3] * (n // 2), [0, 0] * (n // 2))   # clean on code-switch
    b = rich("b", [3, 2] * (n // 2), [4, 5] * (n // 2))   # bad on code-switch
    outcome = decide(
        {"a": a, "b": b}, primary="wer", guardrail_metric="wer",
        guardrail_max=0.5, cost_usd={"a": 9.99, "b": 0.01}, resamples=RESAMPLES,
    )
    assert set(outcome["indistinguishable_from_leader"]) == {"a", "b"}
    # b is far cheaper; the declared order must still pick a on code-switch WER.
    assert outcome["winner"] == "a"
    assert any("cs_wer" in step for step in outcome["tie_break_steps"])
    assert "cost" not in outcome["basis"]


def test_cost_is_reached_only_after_every_quality_metric_ties():
    n = 8
    a = rich("pricey", [2, 3] * (n // 2), [1, 1] * (n // 2))
    b = rich("cheap", [3, 2] * (n // 2), [1, 1] * (n // 2))
    outcome = decide(
        {"pricey": a, "cheap": b}, primary="wer", guardrail_metric="wer",
        guardrail_max=0.5, cost_usd={"pricey": 4.10, "cheap": 0.90},
        resamples=RESAMPLES,
    )
    assert outcome["winner"] == "cheap"
    assert "not a quality judgement" in outcome["basis"]
    assert any("cs_wer" in step for step in outcome["tie_break_steps"])


def test_no_winner_when_everything_ties_and_no_cost_is_supplied():
    n = 8
    a = rich("a", [2, 3] * (n // 2), [1, 1] * (n // 2))
    b = rich("b", [3, 2] * (n // 2), [1, 1] * (n // 2))
    outcome = decide(
        {"a": a, "b": b}, primary="wer", guardrail_metric="wer",
        guardrail_max=0.5, resamples=RESAMPLES,
    )
    assert outcome["winner"] is None
    assert "indistinguishable on every declared metric" in outcome["basis"]
