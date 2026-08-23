"""Paired bootstrap confidence intervals over segments.

Two engines transcribing the same hour are not two independent samples: a
segment with cross-talk is hard for both. Resampling *segments* and comparing
the two engines on each resampled corpus removes that shared difficulty from
the comparison, which is why the interval is on the paired difference rather
than on either engine's own score.

The reporting rule is fixed here, before any results exist:

* If the 95 % interval on the difference contains 0, the data do **not**
  establish a winner between those two engines. We say so, and the tie-break
  in `PREREGISTRATION.md` decides — on cost, not on the point estimate.
* Point estimates are always published with their interval. A ranking whose
  neighbouring intervals overlap is presented as a band, not as places 1 and 2.

Seeded, so a reader re-running the harness gets the same interval.

Stdlib only.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence

from .metrics import LOWER_IS_BETTER, SegmentScore, aggregate

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 20260823
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Interval:
    point: float | None
    low: float | None
    high: float | None
    confidence: float
    resamples: int

    @property
    def measured(self) -> bool:
        return self.point is not None


@dataclass(frozen=True)
class Comparison:
    metric: str
    engine_a: str
    engine_b: str
    difference: Interval
    #: `a`, `b`, or `None` when the interval contains zero.
    better: str | None
    segments: int

    @property
    def indistinguishable(self) -> bool:
        return self.better is None

    def sentence(self) -> str:
        d = self.difference
        point, low, high = d.point, d.low, d.high
        if point is None or low is None or high is None:
            return f"{self.metric}: not measurable on this corpus."
        span = f"[{low:+.4f}, {high:+.4f}]"
        if self.indistinguishable:
            return (
                f"{self.metric}: {self.engine_a} vs {self.engine_b} differ by "
                f"{point:+.4f} {span} — the interval contains 0, so these data "
                f"do not establish a winner; the pre-declared tie-break applies."
            )
        return (
            f"{self.metric}: {self.better} is better by {abs(point):.4f} "
            f"{span} over {self.segments} paired segments."
        )


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile; `q` in [0, 1]."""
    if not sorted_values:
        raise ValueError("empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _pooled(scores: Sequence[SegmentScore], metric: str) -> float | None:
    value = aggregate(scores).get(metric)
    return None if value is None else float(value)


def paired_bootstrap(
    metric: str,
    scores_a: Sequence[SegmentScore],
    scores_b: Sequence[SegmentScore],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Comparison:
    """Bootstrap the paired difference `b - a` in a pooled metric.

    The two score lists must cover the same segments in the same order: the
    pairing is the whole point, and silently zipping mismatched corpora would
    produce a confident number about nothing.
    """
    ids_a = [s.segment_id for s in scores_a]
    ids_b = [s.segment_id for s in scores_b]
    if ids_a != ids_b:
        raise ValueError("paired bootstrap needs identical segment ids in order")
    if not ids_a:
        raise ValueError("no segments to compare")
    engine_a = scores_a[0].engine
    engine_b = scores_b[0].engine

    base_a, base_b = _pooled(scores_a, metric), _pooled(scores_b, metric)
    if base_a is None or base_b is None:
        empty = Interval(None, None, None, confidence, resamples)
        return Comparison(metric, engine_a, engine_b, empty, None, len(ids_a))

    rng = random.Random(seed)
    n = len(ids_a)
    differences: list[float] = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        sample_a = [scores_a[i] for i in picks]
        sample_b = [scores_b[i] for i in picks]
        value_a, value_b = _pooled(sample_a, metric), _pooled(sample_b, metric)
        if value_a is None or value_b is None:
            # A resample can miss every segment that carried the metric (e.g.
            # no code-switched span). Dropping it is honest; substituting 0
            # would pull the interval towards a false tie.
            continue
        differences.append(value_b - value_a)

    if not differences:
        empty = Interval(None, None, None, confidence, resamples)
        return Comparison(metric, engine_a, engine_b, empty, None, n)

    differences.sort()
    tail = (1 - confidence) / 2
    interval = Interval(
        point=base_b - base_a,
        low=_percentile(differences, tail),
        high=_percentile(differences, 1 - tail),
        confidence=confidence,
        resamples=len(differences),
    )

    difference = base_b - base_a
    better: str | None = None
    if interval.low is not None and interval.high is not None:
        if interval.low > 0 or interval.high < 0:
            b_is_better = difference < 0 if metric in LOWER_IS_BETTER else difference > 0
            better = engine_b if b_is_better else engine_a
    return Comparison(metric, engine_a, engine_b, interval, better, n)


def bootstrap_interval(
    metric: str,
    scores: Sequence[SegmentScore],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Interval:
    """Confidence interval on a single engine's pooled metric."""
    point = _pooled(scores, metric)
    if point is None or not scores:
        return Interval(None, None, None, confidence, resamples)
    rng = random.Random(seed)
    n = len(scores)
    samples: list[float] = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        value = _pooled([scores[i] for i in picks], metric)
        if value is not None:
            samples.append(value)
    if not samples:
        return Interval(point, None, None, confidence, 0)
    samples.sort()
    tail = (1 - confidence) / 2
    return Interval(
        point=point,
        low=_percentile(samples, tail),
        high=_percentile(samples, 1 - tail),
        confidence=confidence,
        resamples=len(samples),
    )


def rank(
    engines: dict[str, Sequence[SegmentScore]],
    metric: str,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> list[tuple[str, Interval]]:
    """Order engines by a metric, best first, each with its interval."""
    intervals = {
        name: bootstrap_interval(metric, scores, resamples=resamples, seed=seed)
        for name, scores in engines.items()
    }
    measured = [(n, i) for n, i in intervals.items() if i.measured]
    unmeasured = [(n, i) for n, i in intervals.items() if not i.measured]
    measured.sort(
        key=lambda item: item[1].point if item[1].point is not None else 0.0,
        reverse=metric not in LOWER_IS_BETTER,
    )
    return measured + unmeasured


def decide(
    engines: dict[str, Sequence[SegmentScore]],
    *,
    primary: str,
    guardrail_metric: str,
    guardrail_max: float,
    cost_usd: dict[str, float] | None = None,
    tie_break: Callable[[list[str]], str] | None = None,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[str, object]:
    """Apply the pre-declared decision rule. See `PREREGISTRATION.md`.

    Returns the winner plus the reasoning, including the engines that could not
    be separated from it — which is the honest output when the corpus is an
    hour long and two engines are close.
    """
    eligible = {}
    rejected = {}
    for name, scores in engines.items():
        guard = aggregate(scores).get(guardrail_metric)
        if guard is None:
            rejected[name] = f"{guardrail_metric} not measurable"
        elif guard > guardrail_max:
            rejected[name] = f"{guardrail_metric}={guard:.4f} exceeds {guardrail_max:.4f}"
        else:
            eligible[name] = scores
    if not eligible:
        return {"winner": None, "reason": "no engine met the guardrail", "rejected": rejected}

    ordered = rank(eligible, primary, resamples=resamples, seed=seed)
    leader = ordered[0][0]
    tied = [leader]
    for name, _ in ordered[1:]:
        comparison = paired_bootstrap(
            primary, eligible[leader], eligible[name], resamples=resamples, seed=seed
        )
        if comparison.indistinguishable:
            tied.append(name)

    winner = leader
    basis = f"best {primary}, separated from all others"
    if len(tied) > 1:
        if cost_usd:
            winner = min(tied, key=lambda n: (cost_usd.get(n, float("inf")), n))
            basis = f"{primary} statistically indistinguishable across {tied}; cheapest chosen"
        elif tie_break:
            winner = tie_break(tied)
            basis = f"{primary} indistinguishable across {tied}; explicit tie-break applied"
        else:
            basis = f"{primary} indistinguishable across {tied}; no tie-break supplied"
            winner = None
    return {
        "winner": winner,
        "basis": basis,
        "ranking": [(n, i.point) for n, i in ordered],
        "indistinguishable_from_leader": tied,
        "rejected": rejected,
        "primary": primary,
        "guardrail": {"metric": guardrail_metric, "max": guardrail_max},
    }
