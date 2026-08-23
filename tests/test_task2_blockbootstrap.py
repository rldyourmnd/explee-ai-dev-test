"""Tests for the paired moving-block bootstrap and multiple-comparison control.

The property under test is restraint. A per-segment bootstrap on correlated
segments produces intervals that are too narrow, so these tests check that the
block version is *wider* on correlated data — that it declines to call a
difference that the naive method would have called — while still detecting a
difference that is genuinely there.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness.bootstrap import (  # noqa: E402
    block_size_sensitivity,
    blocks_per_duration,
    bootstrap_two_sided_p,
    holm_adjust,
    paired_bootstrap,
    paired_moving_block,
)
from harness.metrics import SegmentScore  # noqa: E402

RESAMPLES = 600


def scores(engine, errors, ref_words=20):
    return [
        SegmentScore(segment_id=f"s{i:03d}", engine=engine, ref_words=ref_words,
                     substitutions=e, hits=ref_words - e)
        for i, e in enumerate(errors)
    ]


def correlated_pair(n=96):
    """A pair whose *difference* is autocorrelated, which is what matters.

    Both engines finding the same stretch hard does not widen a *paired*
    interval — that difficulty cancels in the difference. What the block
    bootstrap has to survive is a difference that persists over a stretch: here
    engine `a` is better across the whole first half and worse across the whole
    second, so the corpus-level difference is ~0 while neighbouring segments
    agree strongly. Resampling segments independently shatters that structure
    and reports a falsely narrow interval.
    """
    a, b = [], []
    for i in range(n):
        first_half = i < n // 2
        a.append(2 if first_half else 8)
        b.append(8 if first_half else 2)
    return scores("a", a), scores("b", b)


def test_block_bootstrap_is_more_conservative_than_per_segment():
    """On bursty data the naive interval is too narrow. This is the defect."""
    a, b = correlated_pair()
    naive = paired_bootstrap("wer", a, b, resamples=RESAMPLES)
    blocked = paired_moving_block("wer", a, b, block_len=8, resamples=RESAMPLES)
    # Both must be measurable for the widths to mean anything; asserting it also
    # narrows the Optionals for the type checker rather than hiding them.
    assert naive.difference.measured and blocked.difference.measured
    naive_low, naive_high = naive.difference.low, naive.difference.high
    blocked_low, blocked_high = blocked.difference.low, blocked.difference.high
    assert naive_low is not None and naive_high is not None
    assert blocked_low is not None and blocked_high is not None
    assert (blocked_high - blocked_low) > (naive_high - naive_low)


def test_a_real_difference_is_still_detected_with_blocks():
    good = scores("good", [0, 1] * 48)
    bad = scores("bad", [9, 10] * 48)
    comparison = paired_moving_block("wer", good, bad, block_len=4, resamples=RESAMPLES)
    assert comparison.better == "good"


def test_both_systems_draw_the_same_blocks():
    """Identical inputs must give exactly zero difference in every resample."""
    a = scores("a", [3, 1, 4, 1, 5, 9, 2, 6] * 6)
    b = scores("b", [3, 1, 4, 1, 5, 9, 2, 6] * 6)
    comparison = paired_moving_block("wer", a, b, block_len=4, resamples=200)
    assert comparison.difference.low == 0.0
    assert comparison.difference.high == 0.0
    assert comparison.indistinguishable


def test_block_length_is_derived_from_audio_duration():
    # 99 units over 2952.8 s is ~29.8 s per unit, so 120 s is 4 units.
    assert blocks_per_duration(99, 2952.821, 120.0) == 4
    assert blocks_per_duration(99, 2952.821, 60.0) == 2
    assert blocks_per_duration(99, 2952.821, 300.0) == 10
    assert blocks_per_duration(0, 100.0, 120.0) == 1       # degenerate, not a crash
    assert blocks_per_duration(10, 100.0, 10_000.0) == 10  # capped at the corpus


def test_pairing_is_enforced_for_blocks():
    with pytest.raises(ValueError):
        paired_moving_block("wer", scores("a", [1, 1, 1]), scores("b", [1, 1]),
                            block_len=2, resamples=50)


def test_sensitivity_ladder_flags_an_unstable_verdict():
    a, b = correlated_pair()
    stability = block_size_sensitivity(
        "wer", a, b, corpus_seconds=2952.821, resamples=RESAMPLES
    )
    # The corpus-level difference is ~0, so no rung should claim a winner.
    assert set(stability.by_block_seconds.values()) == {None}
    assert stability.stable


def test_an_unstable_verdict_is_reported_as_unstable():
    from harness.bootstrap import Stability

    unstable = Stability("term_f1", "a", "b", {60.0: "a", 120.0: None, 300.0: None})
    assert not unstable.stable
    assert "UNSTABLE" in unstable.sentence()


# --- Holm ---------------------------------------------------------------------

def test_holm_rejects_fewer_than_uncorrected_alpha():
    family = {"vs1": 0.001, "vs2": 0.02, "vs3": 0.04, "vs4": 0.049}
    survives = holm_adjust(family, alpha=0.05)
    assert survives["vs1"] is True       # 0.001 <= 0.05/4
    assert survives["vs2"] is False      # 0.02 > 0.05/3, and step-down stops here
    assert survives["vs3"] is False
    assert survives["vs4"] is False
    # Uncorrected, all four would have "passed" at 0.05.
    assert sum(survives.values()) < len(family)


def test_holm_is_step_down_not_per_comparison():
    family = {"a": 0.01, "b": 0.30, "c": 0.03}
    survives = holm_adjust(family, alpha=0.05)
    assert survives["a"] is True         # 0.01 <= 0.05/3 = 0.0167
    assert survives["c"] is False        # 0.03 > 0.05/2 = 0.025 -> step-down stops
    assert survives["b"] is False        # and everything larger fails with it


def test_two_sided_p_is_small_for_a_real_difference_and_large_for_none():
    good = scores("good", [0, 1] * 48)
    bad = scores("bad", [9, 10] * 48)
    assert bootstrap_two_sided_p("wer", good, bad, block_len=4, resamples=RESAMPLES) < 0.05

    a, b = correlated_pair()
    assert bootstrap_two_sided_p("wer", a, b, block_len=8, resamples=RESAMPLES) > 0.05
