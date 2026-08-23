# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Replay the captured window under varied thresholds and score each setting.

Every threshold in `monitor.POLICY` is a choice nobody specified. Left as bare
constants they are magic numbers; measured against the window they become a
defended choice with a stated cost. This regenerates
`task1-spend-observability/POLICY-SENSITIVITY.md`.

The "missed" column is scored against a ground truth computed straight from the
raw log -- runs of consecutive failed polls -- without reference to any
threshold, so a miss is a miss against the data rather than against the
monitor's own opinion.

Usage:
    uv run tools/policy_sensitivity.py > task1-spend-observability/POLICY-SENSITIVITY.md
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "task1-spend-observability" / "data" / "raw_samples.jsonl"

_spec = importlib.util.spec_from_file_location(
    "monitor", REPO / "task1-spend-observability" / "monitor.py")
if _spec is None or _spec.loader is None:
    raise SystemExit("monitor.py is not loadable")
m = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

# A ground-truth outage: enough consecutive failed polls to be a real gap rather
# than the 1-2 poll transients the API produces constantly.
GROUND_TRUTH_MIN_POLLS = 10


def ground_truth_outages() -> list[tuple[str, Any, float, int]]:
    per: dict[str, list[tuple[Any, bool]]] = defaultdict(list)
    with open(RAW, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("kind") != "balance":
                continue
            reading = m.read_sample(record)
            if reading is not None:
                per[reading.provider].append((reading.ts, reading.state == m.STATE_OK))

    outages = []
    for provider, seq in per.items():
        seq.sort()
        index = 0
        while index < len(seq):
            if seq[index][1]:
                index += 1
                continue
            end = index
            while end < len(seq) and not seq[end][1]:
                end += 1
            length = end - index
            if length >= GROUND_TRUTH_MIN_POLLS:
                duration = (seq[end - 1][0] - seq[index][0]).total_seconds()
                outages.append((provider, seq[index][0], duration, length))
            index = end
    return outages


def run(label: str, policy: dict[str, Any] | None = None,
        baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replay the whole window under one configuration, into throwaway state."""
    workdir = Path(tempfile.mkdtemp())
    # setattr rather than attribute assignment: `m` is a dynamically loaded
    # module, so a static checker cannot know these names exist on it.
    saved_policy, saved_baseline = m.POLICY, m.BASELINE
    try:
        if policy:
            setattr(m, "POLICY", replace(m.POLICY, **policy))
        if baseline:
            setattr(m, "BASELINE", replace(m.BASELINE, **baseline))
        store = m.Store(str(workdir / "s.sqlite"))
        alerts = workdir / "a.jsonl"
        ingestor = m.Ingestor(store, m.Alerter(store, str(alerts)), str(RAW))
        ingestor.replay()
        if ingestor.last_ingest_wall:
            ingestor.maybe_evaluate(ingestor.last_ingest_wall, force=True)
        lines = m.read_alert_lines(str(alerts))
    finally:
        setattr(m, "POLICY", saved_policy)
        setattr(m, "BASELINE", saved_baseline)
        shutil.rmtree(workdir, ignore_errors=True)

    bands = Counter((x["rule"], x["provider"], x["evidence"].get("band")) for x in lines)
    return {
        "label": label,
        "lines": len(lines),
        "incidents": len({(x["rule"], x["provider"]) for x in lines}),
        "restatements": sum(n - 1 for n in bands.values() if n > 1),
        "by_rule": dict(Counter(x["rule"] for x in lines)),
        "unavailable_providers": {x["provider"] for x in lines if x["rule"] == "unavailable"},
    }


def row(result: dict[str, Any], truth_providers: set[str]) -> str:
    missed = sorted(truth_providers - result["unavailable_providers"])
    return (f"| {result['label']:<32} | {result['lines']:>5} | {result['incidents']:>9} | "
            f"{result['restatements']:>12} | {len(missed):>6} |")


def main() -> int:
    if not RAW.exists():
        raise SystemExit(f"no raw log at {RAW}; rsync it from the collector first")

    records = sum(1 for line in open(RAW, encoding="utf-8") if line.strip())
    first = last = None
    with open(RAW, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ts = json.loads(line).get("ts")
                first = first or ts
                last = ts
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown"

    truth = ground_truth_outages()
    truth_providers = {p for p, _, _, _ in truth}

    print("# Policy sensitivity")
    print()
    print("Every threshold in `POLICY` is a choice nobody specified. Left as bare")
    print("constants they are magic numbers; measured against the window they become a")
    print("defended choice with a stated cost.")
    print()
    print("| provenance | |")
    print("|---|---|")
    print(f"| raw records | {records:,} |")
    print(f"| window | `{first}` -> `{last}` |")
    print(f"| repository | `{commit}` |")
    print("| regenerate | `uv run tools/policy_sensitivity.py` |")
    print()
    print(f"Ground truth, computed from the raw log without reference to any threshold: "
          f"**{len(truth)} outages** of {GROUND_TRUTH_MIN_POLLS}+ consecutive failed polls, "
          f"across **{len(truth_providers)} of 15 providers**. Longest first:")
    print()
    print("| provider | started | polls | duration |")
    print("|---|---|---:|---:|")
    for provider, start, duration, length in sorted(truth, key=lambda x: -x[2])[:10]:
        print(f"| `{provider}` | {m.iso(start)} | {length} | {duration / 60:.1f} min |")
    print()

    print("## Unavailability tolerance")
    print()
    print("| setting | lines | incidents | restatements | missed |")
    print("|---|---:|---:|---:|---:|")
    for minutes in (5, 10, 15, 20):
        print(row(run(f"{minutes} min", policy={"unavailable_alert_s": minutes * 60.0}),
                  truth_providers))
    print()
    print(f"`missed` counts providers with a ground-truth outage that received no "
          f"`unavailable` line. It varies only with this setting; in the tables below it "
          f"is constant at {len(truth_providers)} and omitted.")
    print()

    print("## Runway lead time")
    print()
    print("| setting | lines | incidents | restatements |")
    print("|---|---:|---:|---:|")
    for crit, warn in ((6, 24), (12, 48), (24, 72), (48, 168)):
        result = run(f"{crit}h critical / {warn}h warning",
                     policy={"runway_critical_h": float(crit),
                             "runway_warning_h": float(warn)})
        print(f"| {result['label']:<32} | {result['lines']:>5} | {result['incidents']:>9} | "
              f"{result['restatements']:>12} |")
    print()

    print("## Materiality bands and the re-fire floor")
    print()
    print("| setting | lines | incidents | restatements |")
    print("|---|---:|---:|---:|")
    for label, policy in (("shipped bands", None),
                          ("re-fire floor 0 s", {"refire_min_gap_s": 0.0}),
                          ("re-fire floor 1 h", {"refire_min_gap_s": 3600.0})):
        result = run(label, policy=policy)
        print(f"| {result['label']:<32} | {result['lines']:>5} | {result['incidents']:>9} | "
              f"{result['restatements']:>12} |")
    print()

    print("## Anomaly sensitivity (k, in MADs)")
    print()
    print("| setting | lines | incidents | burn_anomaly lines |")
    print("|---|---:|---:|---:|")
    for k in (3.0, 4.0, 6.0, 8.0, 12.0):
        result = run(f"k = {k:g}", baseline={"anomaly_k": k})
        print(f"| {result['label']:<32} | {result['lines']:>5} | {result['incidents']:>9} | "
              f"{result['by_rule'].get('burn_anomaly', 0):>18} |")
    print()

    print("## Minimum evidence before a projection may fire")
    print()
    print("| setting | lines | incidents |")
    print("|---|---:|---:|")
    for span in (0.0, 600.0, 1800.0, 3600.0):
        result = run(f"{span:.0f} s", baseline={"min_projection_span_s": span})
        print(f"| {result['label']:<32} | {result['lines']:>5} | {result['incidents']:>9} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
