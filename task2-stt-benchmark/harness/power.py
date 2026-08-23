"""Can one hour of audio detect the difference we care about?

A null result is only informative if the test could have found an effect. This
module simulates two systems that differ by a known amount, runs the *same*
paired moving-block bootstrap the real comparison uses, and reports how often
it detects the difference.

Run before believing "statistically indistinguishable". If an hour cannot
separate 3–5 points of term F1, the honest report says the corpus is too small
to answer that question — not that the engines are equal.

The simulation borrows its structure from the real corpus: the per-unit counts
of reference term occurrences come from an actual scoring run, so the units
have the same sizes and the same emptiness pattern as the data. Only the hits
are synthetic.

Stdlib only.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from .bootstrap import (
    BLOCK_SECONDS_PRIMARY,
    blocks_per_duration,
    paired_moving_block,
)
from .metrics import SegmentScore

DEFAULT_TRIALS = 200
DEFAULT_DELTAS = (0.03, 0.05, 0.10)


@dataclass(frozen=True)
class PowerResult:
    metric: str
    delta: float
    trials: int
    detections: int
    #: How often the detected direction was the wrong one.
    sign_errors: int

    @property
    def power(self) -> float:
        return self.detections / self.trials if self.trials else 0.0

    def sentence(self) -> str:
        return (
            f"A true {self.delta:.0%} difference in {self.metric} is detected "
            f"{self.power:.0%} of the time on this corpus "
            f"({self.detections}/{self.trials} trials)."
        )


def _synthesise(
    engine: str,
    template: Sequence[SegmentScore],
    recall: float,
    rng: random.Random,
) -> list[SegmentScore]:
    """Build scores with a target term recall, on the real corpus's shape."""
    built: list[SegmentScore] = []
    for unit in template:
        ref_occ = unit.term_ref_occurrences
        hits = sum(1 for _ in range(ref_occ) if rng.random() < recall)
        built.append(
            SegmentScore(
                segment_id=unit.segment_id,
                engine=engine,
                ref_words=unit.ref_words,
                hits=unit.hits,
                term_ref_occurrences=ref_occ,
                # Precision held fixed at the template's level so the simulated
                # difference is in recall alone; F1 then moves with it.
                term_hyp_occurrences=max(hits, unit.term_hyp_occurrences),
                term_hits=hits,
            )
        )
    return built


def simulate(
    template: Sequence[SegmentScore],
    *,
    corpus_seconds: float,
    metric: str = "term_f1",
    baseline_recall: float = 0.40,
    deltas: Sequence[float] = DEFAULT_DELTAS,
    trials: int = DEFAULT_TRIALS,
    resamples: int = 400,
    seed: int = 20260824,
    block_seconds: float = BLOCK_SECONDS_PRIMARY,
) -> list[PowerResult]:
    """Detection probability for each simulated difference.

    `resamples` is lower than the reporting run's 10 000 on purpose: this is a
    power curve over hundreds of trials, and the bootstrap's own noise at 400
    resamples is far below the trial-to-trial variation being measured.
    """
    block_len = blocks_per_duration(len(template), corpus_seconds, block_seconds)
    rng = random.Random(seed)
    results: list[PowerResult] = []
    for delta in deltas:
        detections = 0
        sign_errors = 0
        for trial in range(trials):
            a = _synthesise("sim-a", template, baseline_recall, rng)
            b = _synthesise("sim-b", template, baseline_recall - delta, rng)
            comparison = paired_moving_block(
                metric, a, b,
                block_len=block_len, resamples=resamples, seed=seed + trial,
            )
            if comparison.better is not None:
                detections += 1
                # `a` has the higher recall, so `a` is the correct answer.
                if comparison.better != "sim-a":
                    sign_errors += 1
        results.append(PowerResult(metric, delta, trials, detections, sign_errors))
    return results
