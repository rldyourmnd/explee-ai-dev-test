# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Score every engine against the publisher reference and apply the frozen rule.

The decision rule, guardrail, primary metric and tie-break order are read from
`harness.bootstrap` exactly as pre-registered. Nothing here chooses a threshold;
this file only executes the one declared in `9fd6ff8`.

Writes `data/results-hlk8s.json` and `data/results-hlk8s.csv`.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness.bootstrap import (  # noqa: E402
    BLOCK_SECONDS_PRIMARY,
    block_size_sensitivity,
    blocks_per_duration,
    bootstrap_interval,
    bootstrap_two_sided_p,
    decide,
    holm_adjust,
    paired_moving_block,
)
from harness.document import score_document  # noqa: E402
from harness.glossary import load as load_glossary  # noqa: E402
from harness.metrics import SegmentScore, aggregate  # noqa: E402
from harness.runner import eligibility  # noqa: E402

RAW = HERE / "data" / "raw-hlk8s"
REFERENCE = HERE / "data" / "reference-hlk8s.json"
MANIFEST = HERE / "data" / "manifest-hlk8s.json"

PRIMARY = "term_f1"
GUARDRAIL_METRIC = "wer"
GUARDRAIL_MAX = 0.30


def load_engine_documents() -> dict[str, dict]:
    """Concatenate each engine's segments, in manifest order, into one text."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    order = [s["id"] for s in manifest["segments"]]
    engines: dict[str, dict] = {}
    for engine_dir in sorted(RAW.iterdir()):
        if not engine_dir.is_dir():
            continue
        parts, latencies, missing = [], [], 0
        for segment_id in order:
            path = engine_dir / f"{segment_id}.json"
            if not path.exists():
                missing += 1
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            parts.append(payload.get("text", ""))
            if payload.get("inference_s") is not None:
                latencies.append(payload["inference_s"])
        engines[engine_dir.name] = {
            "text": " ".join(parts),
            "segments": len(order) - missing,
            "missing": missing,
            "median_inference_s": statistics.median(latencies) if latencies else None,
            "total_inference_s": round(sum(latencies), 1) if latencies else None,
        }
    return engines


def main() -> int:
    glossary = load_glossary()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    engines = load_engine_documents()
    if not engines:
        print("no engine output", file=sys.stderr)
        return 1

    # Annotated as Sequence, not list: dict is invariant in its value type, so
    # dict[str, list[...]] will not satisfy decide()'s dict[str, Sequence[...]].
    scores: dict[str, Sequence[SegmentScore]] = {
        name: score_document(name, reference["text"], data["text"], glossary)
        for name, data in engines.items()
    }
    pooled = {name: aggregate(s) for name, s in scores.items()}

    outcome = decide(
        scores,
        primary=PRIMARY,
        guardrail_metric=GUARDRAIL_METRIC,
        guardrail_max=GUARDRAIL_MAX,
    )

    intervals = {
        name: bootstrap_interval(PRIMARY, s) for name, s in scores.items()
    }
    wer_intervals = {name: bootstrap_interval("wer", s) for name, s in scores.items()}

    # The frozen guardrail may reject every engine — on an edited reference it
    # does, because raw WER is inflated for all of them. That verdict stands as
    # declared and is reported; the primary-metric comparison is still computed
    # and published, clearly marked as a ranking that no engine's guardrail
    # passed. Moving the threshold now would be exactly the post-hoc tuning the
    # pre-registration exists to prevent.
    ranked_by_primary = sorted(
        scores, key=lambda n: -(pooled[n].get(PRIMARY) or -1.0)
    )
    declared_winner = outcome.get("winner")
    leader = declared_winner if isinstance(declared_winner, str) else ranked_by_primary[0]
    # Moving-block, not per-segment: segments of one talk are correlated, and
    # resampling them independently reports intervals that are too narrow.
    corpus_seconds = float(
        json.loads(MANIFEST.read_text(encoding="utf-8"))["total_segment_duration_s"]
    )
    unit_count = len(next(iter(scores.values())))
    block_len = blocks_per_duration(unit_count, corpus_seconds, BLOCK_SECONDS_PRIMARY)

    comparisons = []
    pvalues: dict[str, float] = {}
    if leader:
        for name in scores:
            if name == leader:
                continue
            comparison = paired_moving_block(
                PRIMARY, scores[leader], scores[name], block_len=block_len
            )
            stability = block_size_sensitivity(
                PRIMARY, scores[leader], scores[name], corpus_seconds=corpus_seconds
            )
            pvalues[name] = bootstrap_two_sided_p(
                PRIMARY, scores[leader], scores[name], block_len=block_len
            )
            comparisons.append({
                "vs": name,
                "sentence": comparison.sentence(),
                "indistinguishable": comparison.indistinguishable,
                "block_stability": stability.sentence(),
                "stable": stability.stable,
                "bootstrap_p": pvalues[name],
            })
    # Holm across the whole family: leader against every rival at 0.05
    # uncorrected would make a false positive likely.
    survives = holm_adjust(pvalues) if pvalues else {}
    for row in comparisons:
        row["significant_after_holm"] = survives.get(row["vs"], False)

    result = {
        "corpus": json.loads(MANIFEST.read_text(encoding="utf-8"))["corpus_id"],
        "reference": {
            "source_url": reference["source_url"],
            "kind": reference["kind"],
            "words": reference["words"],
        },
        "glossary_fingerprint": glossary.fingerprint,
        "primary": PRIMARY,
        "guardrail": {"metric": GUARDRAIL_METRIC, "max": GUARDRAIL_MAX},
        "decision": outcome,
        "eligibility": eligibility(scores, corpus_size=len(next(iter(scores.values())))),
        "engines": {
            name: {
                **{k: v for k, v in pooled[name].items()},
                "median_inference_s": engines[name]["median_inference_s"],
                "total_inference_s": engines[name]["total_inference_s"],
                "segments": engines[name]["segments"],
                "missing": engines[name]["missing"],
                f"{PRIMARY}_ci": [intervals[name].low, intervals[name].high],
                "wer_ci": [wer_intervals[name].low, wer_intervals[name].high],
            }
            for name in sorted(scores)
        },
        "paired_vs_leader": comparisons,
        "bootstrap": {
            "method": "paired moving-block",
            "primary_block_seconds": BLOCK_SECONDS_PRIMARY,
            "block_units": block_len,
            "corpus_seconds": corpus_seconds,
            "multiple_comparison_correction": "Holm, alpha=0.05",
        },
        "primary_ranking": ranked_by_primary,
        "guardrail_note": (
            "The 0.30 WER guardrail was declared for a verbatim reference. This "
            "reference is the publisher's edited transcript: fillers and false "
            "starts are removed, so every engine's raw WER is inflated by words "
            "that were genuinely spoken but are absent from the reference. Under "
            "the frozen rule no engine clears it, and that verdict is reported "
            "as declared rather than rescued by moving the threshold."
        ),
    }
    (HERE / "data" / "results-hlk8s.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"reference: {reference['words']} words, {len(next(iter(scores.values())))} blocks")
    for name in sorted(pooled, key=lambda n: -(pooled[n].get("term_f1") or 0)):
        p = pooled[name]
        print(
            f"{name:34s} termF1={_f(p.get('term_f1'))} recall={_f(p.get('term_recall'))} "
            f"prec={_f(p.get('term_precision'))} WER={_f(p.get('wer'))} "
            f"csWER={_f(p.get('cs_wer'))} lat2cyr={_f(p.get('latin_to_cyrillic_rate'))} "
            f"halluc={_f(p.get('hallucination_rate'))}"
        )
    print("\ndecision:", json.dumps(outcome, ensure_ascii=False)[:600])
    print(f"\nmoving-block bootstrap: {block_len} units = "
          f"{BLOCK_SECONDS_PRIMARY:.0f}s blocks over {corpus_seconds:.0f}s")
    for c in comparisons:
        print(" ", c["sentence"])
        print("    ", c["block_stability"])
        print(f"     p={c['bootstrap_p']:.4f} holm_significant={c['significant_after_holm']}")
    return 0


def _f(value):
    return "  n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
