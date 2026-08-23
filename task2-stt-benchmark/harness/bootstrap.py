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

#: The tie-break order from `PREREGISTRATION.md` §4, as data. Cost and latency
#: come after all three, and are applied in `_apply_tie_break`, not here.
TIE_BREAK_METRICS = (
    "cs_wer",
    "latin_to_cyrillic_rate",
    "hallucination_rate",
)

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


#: Moving-block bootstrap settings, adopted 2026-08-24 after the methodology
#: review. See `MOVING_BLOCK_RATIONALE`.
BLOCK_SECONDS_PRIMARY = 120.0
BLOCK_SECONDS_LADDER = (60.0, 180.0, 300.0)
BLOCK_SEED = 20260824

MOVING_BLOCK_RATIONALE = """
Segments of one talk are not independent observations. Same speaker, same
microphone, same acoustic path, same topic — and technical terms arrive in
bursts, so an error in one segment predicts an error in its neighbour. Drawing
99 units independently treats correlated data as 99 independent draws, which
understates the variance and can manufacture a significant difference that is
not there. Resampling contiguous blocks keeps the local correlation inside the
resampled unit, so the interval reflects it.
"""


def blocks_per_duration(
    unit_count: int, corpus_seconds: float, block_seconds: float
) -> int:
    """How many contiguous scoring units make up `block_seconds` of audio."""
    if unit_count <= 0 or corpus_seconds <= 0:
        return 1
    seconds_per_unit = corpus_seconds / unit_count
    return max(1, min(unit_count, round(block_seconds / seconds_per_unit)))


def _moving_block_indices(
    rng: random.Random, n: int, block_len: int
) -> list[int]:
    """Circular moving-block resample of `n` indices in blocks of `block_len`."""
    picked: list[int] = []
    while len(picked) < n:
        start = rng.randrange(n)
        picked.extend((start + offset) % n for offset in range(block_len))
    return picked[:n]


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


def paired_moving_block(
    metric: str,
    scores_a: Sequence[SegmentScore],
    scores_b: Sequence[SegmentScore],
    *,
    block_len: int,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = BLOCK_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Comparison:
    """Paired moving-block bootstrap on the difference `b - a`.

    Both systems draw the **same** blocks — that is what makes it paired, and
    what removes the shared difficulty of a hard stretch of audio from the
    comparison. Ratios are recomputed from pooled counts inside `aggregate`,
    never by averaging per-segment ratios, because the mean of per-segment F1
    is a different quantity from corpus F1.
    """
    ids_a = [s.segment_id for s in scores_a]
    if ids_a != [s.segment_id for s in scores_b]:
        raise ValueError("paired bootstrap needs identical segment ids in order")
    if not ids_a:
        raise ValueError("no segments to compare")
    if block_len < 1:
        raise ValueError("block_len must be at least 1")

    engine_a, engine_b = scores_a[0].engine, scores_b[0].engine
    base_a, base_b = _pooled(scores_a, metric), _pooled(scores_b, metric)
    if base_a is None or base_b is None:
        empty = Interval(None, None, None, confidence, resamples)
        return Comparison(metric, engine_a, engine_b, empty, None, len(ids_a))

    rng = random.Random(seed)
    n = len(ids_a)
    differences: list[float] = []
    for _ in range(resamples):
        picks = _moving_block_indices(rng, n, block_len)
        value_a = _pooled([scores_a[i] for i in picks], metric)
        value_b = _pooled([scores_b[i] for i in picks], metric)
        if value_a is None or value_b is None:
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


@dataclass(frozen=True)
class Stability:
    """Does the verdict survive the block-size sensitivity ladder?"""

    metric: str
    engine_a: str
    engine_b: str
    by_block_seconds: dict[float, str | None]

    @property
    def stable(self) -> bool:
        verdicts = set(self.by_block_seconds.values())
        return len(verdicts) == 1

    def sentence(self) -> str:
        if self.stable:
            verdict = next(iter(self.by_block_seconds.values()))
            outcome = verdict or "no separation"
            return (
                f"{self.metric}: {outcome} — stable across block sizes "
                f"{sorted(self.by_block_seconds)}."
            )
        return (
            f"{self.metric}: UNSTABLE — the verdict changes with block size "
            f"({self.by_block_seconds}). The conclusion is not supported by "
            f"these data and is reported as unstable."
        )


def block_size_sensitivity(
    metric: str,
    scores_a: Sequence[SegmentScore],
    scores_b: Sequence[SegmentScore],
    *,
    corpus_seconds: float,
    block_seconds: Sequence[float] = (BLOCK_SECONDS_PRIMARY, *BLOCK_SECONDS_LADDER),
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = BLOCK_SEED,
) -> Stability:
    """Run the ladder. A verdict that moves with block size is not a verdict."""
    verdicts: dict[float, str | None] = {}
    for seconds in sorted(block_seconds):
        block_len = blocks_per_duration(len(scores_a), corpus_seconds, seconds)
        comparison = paired_moving_block(
            metric, scores_a, scores_b,
            block_len=block_len, resamples=resamples, seed=seed,
        )
        verdicts[seconds] = comparison.better
    return Stability(metric, scores_a[0].engine, scores_b[0].engine, verdicts)


def holm_adjust(pvalue_like: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down on a family of comparisons.

    Takes a mapping of comparison name to its "p-value-like" quantity — here the
    bootstrap two-sided tail probability that the difference is zero — and
    returns which comparisons survive at family-wise `alpha`. Comparing one
    leader against seven rivals at 0.05 uncorrected makes a false positive more
    likely than not; Holm is uniformly more powerful than Bonferroni and just as
    valid.
    """
    ordered = sorted(pvalue_like.items(), key=lambda kv: kv[1])
    m = len(ordered)
    survives: dict[str, bool] = {}
    rejected_so_far = True
    for rank_index, (name, p) in enumerate(ordered):
        threshold = alpha / (m - rank_index)
        if rejected_so_far and p <= threshold:
            survives[name] = True
        else:
            # Holm is step-down: once one fails, every larger p-value fails too.
            rejected_so_far = False
            survives[name] = False
    return survives


def bootstrap_two_sided_p(
    metric: str,
    scores_a: Sequence[SegmentScore],
    scores_b: Sequence[SegmentScore],
    *,
    block_len: int,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = BLOCK_SEED,
) -> float:
    """Two-sided bootstrap tail probability that the paired difference is zero."""
    ids_a = [s.segment_id for s in scores_a]
    if ids_a != [s.segment_id for s in scores_b]:
        raise ValueError("paired bootstrap needs identical segment ids in order")
    rng = random.Random(seed)
    n = len(ids_a)
    base_a, base_b = _pooled(scores_a, metric), _pooled(scores_b, metric)
    if base_a is None or base_b is None:
        return 1.0
    observed = base_b - base_a
    differences: list[float] = []
    for _ in range(resamples):
        picks = _moving_block_indices(rng, n, block_len)
        value_a = _pooled([scores_a[i] for i in picks], metric)
        value_b = _pooled([scores_b[i] for i in picks], metric)
        if value_a is not None and value_b is not None:
            differences.append(value_b - value_a)
    if not differences:
        return 1.0
    # Centre the resampled distribution on zero and ask how often it reaches the
    # observed magnitude.
    centre = sum(differences) / len(differences)
    extreme = sum(1 for d in differences if abs(d - centre) >= abs(observed))
    return (extreme + 1) / (len(differences) + 1)


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
    steps: list[str] = []
    if len(tied) > 1:
        winner, basis, steps = _apply_tie_break(
            tied, eligible, cost_usd, tie_break, resamples, seed
        )
    return {
        "winner": winner,
        "basis": basis,
        "tie_break_steps": steps,
        "ranking": [(n, i.point) for n, i in ordered],
        "indistinguishable_from_leader": tied,
        "rejected": rejected,
        "primary": primary,
        "guardrail": {"metric": guardrail_metric, "max": guardrail_max},
    }


def _apply_tie_break(
    tied: list[str],
    engines: dict[str, Sequence[SegmentScore]],
    cost_usd: dict[str, float] | None,
    explicit: Callable[[list[str]], str] | None,
    resamples: int,
    seed: int,
) -> tuple[str | None, str, list[str]]:
    """Walk the pre-declared tie-break order, one metric at a time.

    Jumping straight from the primary metric to "cheapest wins" — which an
    earlier version did — silently discarded the three quality metrics the
    pre-registration promised to consult first, and cost is the *fourth* step,
    not the first. The order is data here so it cannot drift from the frozen
    document again.
    """
    steps: list[str] = []
    remaining = list(tied)
    for metric in TIE_BREAK_METRICS:
        if len(remaining) <= 1:
            break
        ordered = rank(
            {n: engines[n] for n in remaining}, metric, resamples=resamples, seed=seed
        )
        measured = [(n, i) for n, i in ordered if i.measured]
        if not measured:
            steps.append(f"{metric}: not measurable, skipped")
            continue
        leader = measured[0][0]
        still_tied = [leader]
        for name, _ in measured[1:]:
            comparison = paired_bootstrap(
                metric, engines[leader], engines[name], resamples=resamples, seed=seed
            )
            if comparison.indistinguishable:
                still_tied.append(name)
        if len(still_tied) < len(remaining):
            steps.append(f"{metric}: separated {leader} from {len(remaining) - len(still_tied)} engine(s)")
            remaining = still_tied
        else:
            steps.append(f"{metric}: all {len(remaining)} still indistinguishable")

    if len(remaining) == 1:
        return remaining[0], f"resolved by tie-break: {'; '.join(steps)}", steps

    # Every quality metric in the declared order failed to separate them. Cost
    # is step 4 of the frozen rule and is reached only here.
    if cost_usd:
        cheapest = min(remaining, key=lambda n: (cost_usd.get(n, float("inf")), n))
        steps.append(f"cost: {cheapest} cheapest of {remaining}")
        return (
            cheapest,
            "quality metrics could not separate these engines; chosen on measured "
            "cost, which is not a quality judgement: " + "; ".join(steps),
            steps,
        )
    if explicit:
        return explicit(remaining), "explicit tie-break applied: " + "; ".join(steps), steps
    return (
        None,
        f"no winner: {remaining} are indistinguishable on every declared metric "
        "and no cost data was supplied",
        steps,
    )
