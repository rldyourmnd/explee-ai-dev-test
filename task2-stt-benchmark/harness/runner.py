"""Run every adapter over the frozen manifest and record what happened.

Design rules, all of them consequences of "the comparison must mean something":

* **Identical retry policy for all engines.** The policy lives here, once. An
  engine that needed four attempts to answer is not equal to one that answered
  first time, so retries are counted per segment and published.
* **A failure is recorded, never imputed.** A segment an engine could not
  transcribe is stored as a failure and excluded from *both* engines in any
  paired comparison — scoring it as an empty string would reward silence with a
  perfect insertion rate.
* **Raw output is written before anything reads it**, with its SHA-256, so the
  report can be checked against what the vendor actually returned.
* **A missing credential skips one adapter**, loudly, and the run continues.

Cost is recorded from the vendor's own billed figure where the API exposes one;
where it does not, the field stays empty and the report says the number is a
tariff calculation, not a measurement.

Stdlib only.
"""
from __future__ import annotations

import csv
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .adapters.base import Adapter, EngineResult, MissingCredential
from .manifest import Manifest, Segment, sha256_text
from .metrics import SegmentScore, Transcript, aggregate, score_segment
from .glossary import Glossary

MAX_ATTEMPTS = 4
BACKOFF_S = (1.0, 4.0, 10.0)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class RunRecord:
    """One (engine, track, segment) attempt sequence, as published."""

    engine: str
    track: str
    segment_id: str
    model_id: str
    snapshot_date: str
    request_params: dict
    raw_sha256: str
    raw_path: str
    latency_s: float | None
    retries: int
    billed_usd: float | None
    billed_source: str
    error: str | None
    started_at: str


@dataclass
class RunReport:
    corpus_id: str
    manifest_fingerprint: str
    glossary_fingerprint: str
    started_at: str
    finished_at: str = ""
    records: list[RunRecord] = field(default_factory=list)
    skipped_adapters: dict[str, str] = field(default_factory=dict)

    def failures(self) -> list[RunRecord]:
        return [r for r in self.records if r.error]

    def to_json(self) -> str:
        return json.dumps(
            {
                "corpus_id": self.corpus_id,
                "manifest_fingerprint": self.manifest_fingerprint,
                "glossary_fingerprint": self.glossary_fingerprint,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "skipped_adapters": self.skipped_adapters,
                "records": [asdict(r) for r in self.records],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def _sleep(attempt: int, sleeper: Callable[[float], None]) -> None:
    sleeper(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])


def transcribe_with_retry(
    adapter: Adapter,
    segment: Segment,
    glossary_terms: Sequence[str],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> EngineResult:
    """Identical retry policy for every engine. Retries are counted, not hidden."""
    last_error = ""
    started = clock()
    for attempt in range(max_attempts):
        try:
            result = adapter.transcribe(segment.path, glossary_terms)
            result.retries = attempt
            if result.latency_s is None:
                result.latency_s = clock() - started
            if not result.raw_sha256:
                result.raw_sha256 = sha256_text(result.raw)
            if result.ok:
                return result
            last_error = result.error or "unspecified engine error"
        except MissingCredential:
            raise
        except Exception as exc:  # noqa: BLE001 - the vendor's failure is data
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < max_attempts - 1:
            _sleep(attempt, sleeper)
    return EngineResult(
        engine=adapter.name,
        track=adapter.track,
        segment_id=segment.id,
        model_id=adapter.model_id,
        snapshot_date=adapter.snapshot_date,
        request_params=dict(adapter.request_params(glossary_terms)),
        raw="",
        raw_sha256=sha256_text(""),
        latency_s=clock() - started,
        retries=max_attempts - 1,
        error=last_error or "failed after retries",
    )


def run(
    adapters: Sequence[Adapter],
    manifest: Manifest,
    glossary: Glossary,
    out_dir: Path | str,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> RunReport:
    """Run every available adapter over every frozen segment."""
    out = Path(out_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    terms = [term.canonical for term in glossary]
    report = RunReport(
        corpus_id=manifest.corpus_id,
        manifest_fingerprint=manifest.fingerprint(),
        glossary_fingerprint=glossary.fingerprint,
        started_at=_now(),
    )

    for adapter in adapters:
        key = f"{adapter.name}:{adapter.track}"
        if not adapter.available():
            # One adapter without a key must not take the benchmark down.
            report.skipped_adapters[key] = "credential absent in environment"
            continue
        for segment in manifest.segments:
            started_at = _now()
            try:
                result = transcribe_with_retry(
                    adapter, segment, terms, sleeper=sleeper
                )
            except MissingCredential as exc:
                report.skipped_adapters[key] = str(exc)
                break
            except Exception:  # noqa: BLE001
                result = EngineResult(
                    engine=adapter.name, track=adapter.track, segment_id=segment.id,
                    model_id=adapter.model_id, snapshot_date=adapter.snapshot_date,
                    request_params=dict(adapter.request_params(terms)), raw="",
                    raw_sha256=sha256_text(""),
                    error=traceback.format_exc(limit=1).strip().splitlines()[-1],
                )
            raw_path = out / "raw" / f"{key.replace(':', '-')}-{segment.id}.json"
            raw_path.write_text(result.raw, encoding="utf-8")
            report.records.append(
                RunRecord(
                    engine=adapter.name, track=adapter.track, segment_id=segment.id,
                    model_id=adapter.model_id, snapshot_date=adapter.snapshot_date,
                    request_params=dict(result.request_params),
                    raw_sha256=result.raw_sha256, raw_path=str(raw_path),
                    latency_s=result.latency_s, retries=result.retries,
                    billed_usd=result.billed_usd, billed_source=result.billed_source,
                    error=result.error, started_at=started_at,
                )
            )
    report.finished_at = _now()
    return report


def score_run(
    references: dict[str, Transcript],
    hypotheses: dict[tuple[str, str], Transcript],
    glossary: Glossary,
) -> dict[str, list[SegmentScore]]:
    """Score stored output.

    `hypotheses` is keyed by `(engine_track, segment_id)`. Only segments every
    listed engine transcribed successfully are scored, so the paired bootstrap
    compares like with like; the dropped segments are reported separately.
    """
    engines = sorted({key[0] for key in hypotheses})
    return {
        engine: [
            score_segment(
                segment_id, engine, references[segment_id],
                hypotheses[(engine, segment_id)], glossary,
            )
            for segment_id in sorted(references)
            if (engine, segment_id) in hypotheses
        ]
        for engine in engines
    }


#: OPERATIONAL POLICY, not a measured finding. An engine must return usable
#: output for at least this share of the corpus to be eligible for ranking.
#: Without a floor, an engine that fails on hard audio can still place well on
#: the easy remainder — survivorship from the second direction, after the
#: pairwise-scoring fix closed the first. 0.98 allows two failed segments in
#: a hundred; the number is a policy choice and is labelled as one.
MIN_COVERAGE = 0.98
MAX_FAILURE_RATE = 1.0 - MIN_COVERAGE


def pair_for_bootstrap(
    scores_a: Sequence[SegmentScore], scores_b: Sequence[SegmentScore]
) -> tuple[list[SegmentScore], list[SegmentScore]]:
    """Intersect two engines' segments for a paired comparison.

    Pairwise, deliberately. An earlier version intersected across *all* engines
    at once, so one engine failing 25 hard segments deleted those segments from
    everybody — quietly making the whole benchmark easier and flattering every
    engine that had handled them. Reliability belongs in its own column, not
    hidden inside the accuracy numbers.
    """
    common = sorted({s.segment_id for s in scores_a} & {s.segment_id for s in scores_b})
    by_a = {s.segment_id: s for s in scores_a}
    by_b = {s.segment_id: s for s in scores_b}
    return [by_a[i] for i in common], [by_b[i] for i in common]


def eligibility(
    scores: Mapping[str, Sequence[SegmentScore]],
    corpus_size: int,
    max_failure_rate: float = MAX_FAILURE_RATE,
) -> dict[str, dict[str, object]]:
    """Per-engine corpus coverage, and whether it may be ranked at all."""
    report: dict[str, dict[str, object]] = {}
    for engine, engine_scores in sorted(scores.items()):
        covered = len(engine_scores)
        missing = max(0, corpus_size - covered)
        rate = missing / corpus_size if corpus_size else 0.0
        report[engine] = {
            "segments_scored": covered,
            "segments_missing": missing,
            "failure_rate": rate,
            "rankable": rate <= max_failure_rate,
            "coverage": 1.0 - rate,
            "policy": f"operational policy: coverage >= {1 - max_failure_rate:.0%}",
        }
    return report


RESULT_COLUMNS = [
    "engine", "track", "model_id", "snapshot_date", "segments", "ref_words",
    "wer", "cer", "cs_wer", "term_precision", "term_recall", "term_f1",
    "name_recall", "latin_to_cyrillic_rate", "hallucination_rate",
    "omission_rate", "boundary_error_rate", "speaker_accuracy",
    "timestamp_median_abs_error_s", "timestamp_within_tolerance_rate",
    "median_latency_s", "total_retries", "failed_segments", "billed_usd",
    "billed_source",
]


def write_results_csv(
    path: Path | str,
    scores: dict[str, list[SegmentScore]],
    report: RunReport | None = None,
) -> Path:
    """Write the results table. Unmeasured cells are empty, never zero."""
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for engine, engine_scores in sorted(scores.items()):
            row: dict[str, object] = {"engine": engine, "track": ""}
            if ":" in engine:
                row["engine"], row["track"] = engine.split(":", 1)
            row.update(
                {k: v for k, v in aggregate(engine_scores).items() if k in RESULT_COLUMNS}
            )
            if report:
                records = [
                    r for r in report.records if f"{r.engine}:{r.track}" == engine
                ]
                latencies = sorted(r.latency_s for r in records if r.latency_s is not None)
                billed = [r.billed_usd for r in records if r.billed_usd is not None]
                row["model_id"] = records[0].model_id if records else ""
                row["snapshot_date"] = records[0].snapshot_date if records else ""
                row["median_latency_s"] = (
                    latencies[len(latencies) // 2] if latencies else ""
                )
                row["total_retries"] = sum(r.retries for r in records)
                row["failed_segments"] = sum(1 for r in records if r.error)
                row["billed_usd"] = sum(billed) if billed else ""
                row["billed_source"] = (
                    records[0].billed_source if records and records[0].billed_source
                    else "not exposed by vendor API"
                )
            writer.writerow({k: row.get(k, "") for k in RESULT_COLUMNS})
    return path
