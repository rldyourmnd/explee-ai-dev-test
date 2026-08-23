"""Tests for the run harness: manifest, retry accounting, results table.

No audio and no vendor account exists yet — the audio source and spend ceiling
are still the human's decisions — so these tests use fake adapters. That is the
point: the harness has to be provably correct *before* money is spent, because
a bug found after a paid run costs a second paid run.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-stt-benchmark"))

from harness import glossary as glossary_module  # noqa: E402
from harness.adapters.base import BaseAdapter, EngineResult, MissingCredential  # noqa: E402
from harness.manifest import (  # noqa: E402
    AudioProperties,
    Manifest,
    Segment,
    fixed_boundaries,
    sha256_text,
)
from harness.metrics import Transcript  # noqa: E402
from harness.runner import (  # noqa: E402
    MAX_ATTEMPTS,
    run,
    score_run,
    transcribe_with_retry,
    write_results_csv,
)


@pytest.fixture(scope="module")
def glossary():
    return glossary_module.load()


def make_manifest(count=2, tmp_path=None):
    segments = [
        Segment(
            id=f"c-{i:04d}", index=i, start_s=i * 30.0, end_s=(i + 1) * 30.0,
            sha256=sha256_text(f"segment-{i}"),
            path=str((tmp_path or Path(".")) / f"c-{i:04d}.wav"),
        )
        for i in range(count)
    ]
    return Manifest(
        corpus_id="c", source_path="corpus.wav", source_sha256=sha256_text("corpus"),
        source_properties=AudioProperties(60.0, 16000, 1, "pcm_s16le", "wav"),
        segments=segments, created_at="2026-08-23T19:00:00Z",
        provenance="fixture; no real audio",
    )


class FakeAdapter(BaseAdapter):
    """Deterministic stand-in for a vendor: fails `fail_times` then answers."""

    def __init__(self, name="fake", track="default", fail_times=0, always_fail=False,
                 text="мы подняли ClickHouse", key_env="FAKE_KEY"):
        super().__init__(
            name=name, track=track, model_id=f"{name}-v1",
            snapshot_date="2026-08-01", api_key_env=key_env,
            supports_terminology=(track == "tuned"),
        )
        self.fail_times = fail_times
        self.always_fail = always_fail
        self.text = text
        self.calls = 0

    def available(self):
        return True

    def transcribe(self, segment_path, glossary_terms):
        self.calls += 1
        if self.always_fail or self.calls <= self.fail_times:
            raise RuntimeError("503 upstream")
        return EngineResult(
            engine=self.name, track=self.track, segment_id=Path(segment_path).stem,
            model_id=self.model_id, snapshot_date=self.snapshot_date,
            request_params=self.request_params(glossary_terms),
            raw='{"text": "%s"}' % self.text,
            transcript=Transcript(self.text), latency_s=0.5,
            billed_usd=0.01, billed_source="vendor usage field",
        )


# --- manifest -----------------------------------------------------------------

def test_boundaries_cover_the_whole_file_without_gaps_or_overlap():
    bounds = fixed_boundaries(95.0, segment_s=30.0)
    assert bounds[0][0] == 0.0
    assert bounds[-1][1] == 95.0
    for (_, end), (start, _) in zip(bounds, bounds[1:]):
        assert end == start


def test_a_final_scrap_is_merged_rather_than_billed_as_a_segment():
    bounds = fixed_boundaries(62.0, segment_s=30.0, minimum_s=5.0)
    assert bounds == [(0.0, 30.0), (30.0, 62.0)]


def test_a_window_keeps_source_absolute_timestamps():
    """A corpus cut from the middle of a recording must stay re-derivable.

    The cut points published in the report are absolute times in the
    publisher's original file, so a reader can reproduce the same segments
    without our copy of the audio.
    """
    bounds = fixed_boundaries(3600.0, segment_s=30.0, offset_s=300.0)
    assert bounds[0] == (300.0, 330.0)
    assert bounds[-1] == (3870.0, 3900.0)
    assert len(bounds) == 120


def test_a_window_outside_the_recording_is_refused():
    from harness.manifest import freeze
    import harness.manifest as manifest_module

    props = AudioProperties(600.0, 16000, 1, "mp3", "mp3")
    original_probe = manifest_module.probe
    manifest_module.probe = lambda _path: props
    try:
        with pytest.raises(ValueError, match="does not fit"):
            freeze("x.mp3", "out", corpus_id="c", provenance="test",
                   window=(300.0, 1200.0))
    finally:
        manifest_module.probe = original_probe


def test_manifest_round_trips_and_fingerprints(tmp_path):
    manifest = make_manifest(tmp_path=tmp_path)
    path = tmp_path / "manifest.json"
    fingerprint = manifest.write(path)
    reloaded = Manifest.load(path)
    assert reloaded.fingerprint() == fingerprint
    assert reloaded.segments[1].sha256 == manifest.segments[1].sha256
    assert reloaded.source_properties.sample_rate == 16000


def test_manifest_requires_provenance():
    from harness.manifest import freeze
    with pytest.raises(ValueError, match="provenance"):
        freeze("nonexistent.wav", "out", corpus_id="c", provenance="  ")


# --- retry and failure accounting ---------------------------------------------

def test_retries_are_counted_not_hidden(glossary):
    adapter = FakeAdapter(fail_times=2)
    segment = make_manifest().segments[0]
    result = transcribe_with_retry(adapter, segment, [], sleeper=lambda _: None)
    assert result.ok
    assert result.retries == 2
    assert result.raw_sha256


def test_a_permanently_failing_engine_produces_a_failure_not_empty_text(glossary):
    adapter = FakeAdapter(always_fail=True)
    segment = make_manifest().segments[0]
    result = transcribe_with_retry(adapter, segment, [], sleeper=lambda _: None)
    assert not result.ok
    assert result.retries == MAX_ATTEMPTS - 1
    assert "503" in (result.error or "")


def test_a_missing_credential_skips_one_adapter_not_the_run(tmp_path, glossary):
    working = FakeAdapter(name="working")
    missing = BaseAdapter(
        name="keyless", track="default", model_id="x", snapshot_date="2026-08-01",
        api_key_env="DEFINITELY_NOT_SET_FOR_THIS_TEST",
    )
    report = run(
        [working, missing], make_manifest(tmp_path=tmp_path), glossary, tmp_path,
        sleeper=lambda _: None,
    )
    assert "keyless:default" in report.skipped_adapters
    assert [r.engine for r in report.records] == ["working", "working"]
    assert report.failures() == []


def test_raw_output_is_stored_before_scoring(tmp_path, glossary):
    report = run(
        [FakeAdapter()], make_manifest(tmp_path=tmp_path), glossary, tmp_path,
        sleeper=lambda _: None,
    )
    for record in report.records:
        stored = Path(record.raw_path).read_text(encoding="utf-8")
        assert sha256_text(stored) == record.raw_sha256
        assert "ClickHouse" in stored


def test_run_report_records_model_identity_and_parameters(tmp_path, glossary):
    report = run(
        [FakeAdapter(track="tuned")], make_manifest(tmp_path=tmp_path), glossary,
        tmp_path, sleeper=lambda _: None,
    )
    record = report.records[0]
    assert record.model_id == "fake-v1"
    assert record.snapshot_date == "2026-08-01"
    assert record.request_params["keyterms"][:1] == ["RAG"]
    assert record.billed_source == "vendor usage field"


def test_no_credential_value_can_reach_a_report(tmp_path, glossary, monkeypatch):
    """A key in the environment must never be serialised into the run record."""
    monkeypatch.setenv("FAKE_KEY", "sk-should-never-appear")
    report = run(
        [FakeAdapter()], make_manifest(tmp_path=tmp_path), glossary, tmp_path,
        sleeper=lambda _: None,
    )
    assert "sk-should-never-appear" not in report.to_json()


def test_require_key_raises_rather_than_returning_empty():
    from harness.adapters.base import require_key
    with pytest.raises(MissingCredential):
        require_key("DEFINITELY_NOT_SET_FOR_THIS_TEST")


# --- scoring and the results table --------------------------------------------

def test_only_segments_every_engine_transcribed_are_scored(glossary):
    references = {
        "s0": Transcript("мы подняли ClickHouse"),
        "s1": Transcript("и настроили Kafka"),
    }
    hypotheses = {
        ("a:default", "s0"): Transcript("мы подняли ClickHouse"),
        ("a:default", "s1"): Transcript("и настроили Kafka"),
        ("b:default", "s0"): Transcript("мы подняли Lead House"),
        # b failed on s1: it must drop out of the paired comparison for *both*.
    }
    scores = score_run(references, hypotheses, glossary)
    assert [s.segment_id for s in scores["a:default"]] == ["s0"]
    assert [s.segment_id for s in scores["b:default"]] == ["s0"]


def test_results_csv_leaves_unmeasured_cells_empty(tmp_path, glossary):
    references = {"s0": Transcript("мы подняли ClickHouse")}
    hypotheses = {("a:default", "s0"): Transcript("мы подняли Lead House")}
    scores = score_run(references, hypotheses, glossary)
    path = write_results_csv(tmp_path / "results.csv", scores)
    rows = path.read_text(encoding="utf-8").splitlines()
    header, row = rows[0].split(","), rows[1].split(",")
    cells = dict(zip(header, row))
    assert cells["engine"] == "a" and cells["track"] == "default"
    assert cells["name_recall"] == "0.0"
    assert cells["speaker_accuracy"] == ""  # no labels: unmeasured, not zero
