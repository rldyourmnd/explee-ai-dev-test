"""Tests for the spend monitor.

The cases worth testing hardest are the ones where a plausible implementation
silently produces fiction rather than failing: `{}` read as a zero balance, a
top-up read as spend, a first/last burn rate across a hole, a flapping provider
read as two hundred incidents. Each of those has a test that asserts the
fabricated answer is *not* produced, using payloads and numbers taken from the
captured window rather than invented ones.
"""
import hashlib
import importlib.util
import json
import statistics
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "monitor", ROOT / "task1-spend-observability" / "monitor.py")
    assert spec is not None and spec.loader is not None, "monitor must be loadable"
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is absent for a hand-built spec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m = _load()

T0 = datetime(2026, 8, 23, 16, 13, 26, tzinfo=timezone.utc)

# Verbatim response bodies from the captured window, one per distinct shape.
SHAPES = {
    "flat_balance": ('{"balance":947.3,"currency":"usd"}', 947.3),
    "nested_wallet": ('{"ok":true,"data":{"wallet":{"amount":304.38,"ccy":"usd"}}}', 304.38),
    "bare_currency_key": ('{"gbp":1992.17}', 1992.17),
    "credits_package": ('{"package":12000,"refresh":"2026-09-01","remaining":10306}', 10306.0),
    "postpaid_credit": ('{"credit":49.66,"unit":"usd"}', 49.66),
    "cost_report": ('{"object":"cost_report","amount_cents":3940,"window":"trailing_24h"}', 39.40),
    "spend_report_24h": ('{"spend_usd_30d":10431.67,"spend_usd_24h":347.72}', 347.72),
}

HTML_504 = ('<!DOCTYPE html>\n<!--[if lt IE 7]> <html class="no-js ie6 oldie" '
            'lang="en-US"> <![endif]-->\n<title>504 Gateway Time-out</title>')

CATALOG = [
    {"provider": "brightdata", "name": "Oxylabs", "pay_model": "prepaid_balance",
     "unit": "usd", "endpoint": "/api/brightdata/balance", "note": "Prepaid USD."},
    {"provider": "findymail", "name": "Hunter", "pay_model": "credits_package",
     "unit": "credits", "endpoint": "/api/findymail/balance", "note": "Credits."},
    {"provider": "vastai", "name": "RunPod", "pay_model": "postpaid",
     "unit": "usd", "endpoint": "/api/vastai/balance", "note": "Postpaid."},
    {"provider": "anthropic", "name": "Anthropic", "pay_model": "spend_report",
     "unit": "usd", "endpoint": "/api/anthropic/balance", "note": "Trailing cost."},
    # A second credits provider and a second USD provider, so aggregation can be
    # tested in both directions: credits must not be summed, dollars must be.
    {"provider": "bounceban", "name": "Kickbox", "pay_model": "credits_package",
     "unit": "credits", "endpoint": "/api/bounceban/balance", "note": "Credits."},
    {"provider": "openai", "name": "OpenAI", "pay_model": "prepaid_balance",
     "unit": "usd", "endpoint": "/api/openai/balance", "note": "Prepaid USD."},
]


# ---------------------------------------------------------------- helpers


def _ts(seconds: float) -> str:
    return m.iso(T0 + timedelta(seconds=seconds))


def _rec(provider, seconds, body='{"balance":1.0,"currency":"usd"}', http=200, latency=110.0):
    return {"ts": _ts(seconds), "kind": "balance", "provider": provider,
            "url": f"/api/{provider}/balance", "http": http, "latency_ms": latency,
            "body": body, "content_type": "application/json"}


def _catalog_rec(seconds, entries=None):
    return {"ts": _ts(seconds), "kind": "catalog", "provider": None,
            "url": "/api/providers", "http": 200, "latency_ms": 350.0,
            "body": json.dumps(entries if entries is not None else CATALOG),
            "content_type": "application/json"}


def _write(path: Path, records) -> Path:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def _pipeline(tmp_path: Path, records, name="raw.jsonl"):
    """Write a synthetic raw log and replay it exactly as the live monitor does."""
    raw = _write(tmp_path / name, records)
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    ingestor = m.Ingestor(store, m.Alerter(store, str(alerts)), str(raw))
    ingestor.replay()
    return store, ingestor, alerts


def _alert_lines(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cycles(builder, count, providers=("brightdata",), start=0.0, step=30.0):
    """Emit `count` sampler cycles, each a catalog record then one poll per provider.

    The catalog is narrowed to the providers actually polled. A catalog that
    advertises providers the log never contains is a genuine incident - the
    monitor rightly treats them as unobservable - so it must not be produced
    here by accident.
    """
    entries = [c for c in CATALOG if c["provider"] in providers]
    assert len(entries) == len(providers), "unknown provider in fixture"
    records = []
    for i in range(count):
        moment = start + i * step
        records.append(_catalog_rec(moment, entries))
        for provider in providers:
            built = builder(provider, i)
            if built is None:
                continue
            body, http = built
            records.append(_rec(provider, moment + 0.5, body=body, http=http))
    return records


# --------------------------------------------------- standalone collection


class _FakeAPI(BaseHTTPRequestHandler):
    """A stand-in for the provider API, so these tests need no network."""

    routes: dict = {}

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        status, body, content_type = self.routes.get(
            self.path, (404, '{"error":"no route"}', "application/json"))
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - base class name
        return


@pytest.fixture
def fake_api():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_standalone_collection_produces_records_the_replay_path_reads(tmp_path, fake_api):
    """The one-file path must feed the same parser, not a parallel one.

    The deliverable is a single file, so `--poll` collects and derives in one
    process. That is only safe if collection emits exactly the record shape the
    ingestor already consumes: two parsers would drift, and the replay path is
    the one every other test exercises.
    """
    _FakeAPI.routes = {
        "/providers": (200, json.dumps([
            {"provider": "brightdata", "name": "Oxylabs", "pay_model": "prepaid_balance",
             "unit": "usd", "endpoint": "/api/brightdata/balance", "note": ""},
        ]), "application/json"),
        "/brightdata/balance": (200, '{"balance":947.30,"currency":"usd"}',
                                "application/json"),
    }
    collector = m.Collector(str(tmp_path / "raw.jsonl"), fake_api, interval=1, timeout=5)
    records = collector.cycle()
    collector.append(records)

    kinds = [r["kind"] for r in records]
    assert kinds == ["catalog", "balance"]

    balance = records[1]
    for key in ("ts", "kind", "provider", "url", "http", "latency_ms", "body", "content_type"):
        assert key in balance, f"record shape is missing {key}"
    reading = m.read_sample(balance)
    assert reading is not None
    assert reading.state == m.STATE_OK
    assert reading.value == pytest.approx(947.30)
    assert reading.shape == "flat_balance"

    # And the file it wrote replays like any other raw log.
    store = m.Store(str(tmp_path / "m.sqlite"))
    ingestor = m.Ingestor(store, m.Alerter(store, str(tmp_path / "a.jsonl")),
                          str(tmp_path / "raw.jsonl"))
    ingestor.replay()
    assert store.coverage()["samples"] == 1
    assert set(store.catalog()) == {"brightdata"}


@pytest.mark.parametrize("status,body,expected_state", [
    (429, '{"error":"rate limited"}', m.STATE_HTTP_ERROR),
    (500, '{"error":"upstream 500"}', m.STATE_HTTP_ERROR),
    (503, '{"error":"upstream 503"}', m.STATE_HTTP_ERROR),
    (504, "<!DOCTYPE html><title>504 Gateway Time-out</title>", m.STATE_UNPARSEABLE),
    (200, "{}", m.STATE_SCHEMA_MISS),
])
def test_standalone_collection_keeps_error_bodies(tmp_path, fake_api, status, body,
                                                  expected_state):
    """urllib raises on 4xx/5xx; the body is data and must survive that."""
    _FakeAPI.routes = {"/x/balance": (status, body, "text/html" if status == 504
                                      else "application/json")}
    collector = m.Collector(str(tmp_path / "raw.jsonl"), fake_api, interval=1, timeout=5)
    record = collector.probe("/x/balance", "balance", "x")
    assert record["http"] == status
    assert record["body"] == body
    assert m.read_sample(record).state == expected_state


def test_standalone_collection_records_pre_truncation_length(tmp_path, fake_api):
    """`body_chars` makes a clip at the 8000 cap detectable after the fact."""
    long_body = '{"note":"' + "x" * 9000 + '"}'
    _FakeAPI.routes = {"/big/balance": (200, long_body, "application/json")}
    collector = m.Collector(str(tmp_path / "raw.jsonl"), fake_api, interval=1, timeout=5)
    record = collector.probe("/big/balance", "balance", "big")
    assert record["body_chars"] == len(long_body)
    assert len(record["body"]) == m.Collector.BODY_CAP
    assert record["body_chars"] > len(record["body"]), "truncation is now detectable"


def test_a_clipped_body_fails_closed_rather_than_yielding_a_wrong_value():
    """The safety property behind the 8000-character cap.

    Nothing in the observed window came within 1,578 characters of the bound, so
    this has not happened — but "it has not happened yet" is not a safety
    argument. Clipping valid JSON almost always produces invalid JSON, which the
    parser rejects, so a truncated body becomes `unparseable` rather than a
    plausible-looking wrong number. That is the difference between a visible gap
    and a fabricated balance.
    """
    full = json.dumps({"balance": 947.30, "currency": "usd", "note": "x" * 9000})
    clipped = full[:m.Collector.BODY_CAP]
    assert len(clipped) < len(full)

    record = _rec("brightdata", 0, body=clipped)
    record["body_chars"] = len(full)
    reading = m.read_sample(record)
    assert reading.state == m.STATE_UNPARSEABLE
    assert reading.value is None, "a clipped body must never produce a value"

    # And the record itself carries enough to diagnose it after the fact.
    assert record["body_chars"] > len(record["body"])


def test_standalone_collection_survives_an_unreachable_api(tmp_path):
    """A dead endpoint is data, not a crash: the loop must keep collecting."""
    collector = m.Collector(str(tmp_path / "raw.jsonl"),
                            "http://127.0.0.1:9", interval=1, timeout=1)
    record = collector.probe("/providers", "catalog")
    assert record["http"] is None
    assert "error" in record
    assert m.read_sample(dict(record, kind="balance", provider="x")).state == \
        m.STATE_TRANSPORT_ERROR


def test_the_collection_loop_keeps_going_and_stops_cleanly(tmp_path, fake_api):
    """`--poll` is a long-running loop, so the loop itself needs testing.

    Everything above exercises one cycle. This exercises the thing that actually
    runs for hours: repeated cycles at an interval, appending as it goes, and
    stopping when asked rather than on the next timer tick.
    """
    _FakeAPI.routes = {
        "/providers": (200, json.dumps([
            {"provider": "brightdata", "pay_model": "prepaid_balance", "unit": "usd"}]),
            "application/json"),
        "/brightdata/balance": (200, '{"balance":900.00,"currency":"usd"}',
                                "application/json"),
    }
    raw = tmp_path / "raw.jsonl"
    collector = m.Collector(str(raw), fake_api, interval=0.2, timeout=5)
    thread = threading.Thread(target=collector.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while collector.cycles < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    collector.stop.set()
    thread.join(timeout=10)

    assert not thread.is_alive(), "the loop must stop when asked"
    assert collector.cycles >= 3, f"expected repeated cycles, got {collector.cycles}"
    records = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
    assert len([r for r in records if r["kind"] == "balance"]) >= 3
    assert all(m.read_sample(r) is not None or r["kind"] == "catalog" for r in records)


def test_the_collection_loop_survives_a_failing_cycle(tmp_path, fake_api, capfd):
    """One bad cycle must not end collection: the window cannot be recreated."""
    _FakeAPI.routes = {
        "/providers": (200, json.dumps([
            {"provider": "brightdata", "pay_model": "prepaid_balance", "unit": "usd"}]),
            "application/json"),
        "/brightdata/balance": (200, '{"balance":900.00,"currency":"usd"}',
                                "application/json"),
    }
    collector = m.Collector(str(tmp_path / "raw.jsonl"), fake_api, interval=0.2, timeout=5)
    calls = {"n": 0}
    real_cycle = collector.cycle

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic cycle failure")
        return real_cycle()

    collector.cycle = flaky  # type: ignore[method-assign]
    thread = threading.Thread(target=collector.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while calls["n"] < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    collector.stop.set()
    thread.join(timeout=10)

    assert calls["n"] >= 3, "the loop stopped after the failing cycle"
    assert "synthetic cycle failure" in capfd.readouterr().err, \
        "a failed cycle must be visible to an operator"


def test_polled_records_are_picked_up_by_the_tailing_ingestor(tmp_path, fake_api):
    """The actual `--poll` shape: one process collecting and deriving at once.

    Collection appends; ingestion tails the same file. This is the integration
    the single-file deliverable depends on, and testing the two halves
    separately would not catch them disagreeing about the file.
    """
    _FakeAPI.routes = {
        "/providers": (200, json.dumps([
            {"provider": "brightdata", "name": "Oxylabs", "pay_model": "prepaid_balance",
             "unit": "usd", "endpoint": "/api/brightdata/balance", "note": ""}]),
            "application/json"),
        "/brightdata/balance": (200, '{"balance":900.00,"currency":"usd"}',
                                "application/json"),
    }
    raw = tmp_path / "raw.jsonl"
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    ingestor = m.Ingestor(store, m.Alerter(store, str(tmp_path / "alerts.jsonl")), str(raw))
    collector = m.Collector(str(raw), fake_api, interval=0.2, timeout=5)

    collector.append(collector.cycle())
    ingest_thread = threading.Thread(target=ingestor.tail, args=(0.1,), daemon=True)
    collect_thread = threading.Thread(target=collector.run, daemon=True)
    ingest_thread.start()
    collect_thread.start()
    try:
        deadline = time.monotonic() + 15
        while store.coverage()["samples"] < 3 and time.monotonic() < deadline:
            time.sleep(0.1)
    finally:
        collector.stop.set()
        ingestor.stop.set()
        collect_thread.join(timeout=10)
        ingest_thread.join(timeout=10)

    coverage = store.coverage()
    assert coverage["samples"] >= 3, \
        f"the ingestor did not pick up polled records: {coverage}"
    assert coverage["ok_samples"] == coverage["samples"], "all should have parsed"
    assert set(store.catalog()) == {"brightdata"}, "the polled catalog must reach the store"


def test_standalone_collection_keeps_polling_after_a_bad_catalog(tmp_path, fake_api):
    """An unparseable catalog must not stop the providers already known."""
    _FakeAPI.routes = {
        "/providers": (200, json.dumps([
            {"provider": "brightdata", "pay_model": "prepaid_balance", "unit": "usd"}]),
            "application/json"),
        "/brightdata/balance": (200, '{"balance":900.00,"currency":"usd"}',
                                "application/json"),
    }
    collector = m.Collector(str(tmp_path / "raw.jsonl"), fake_api, interval=1, timeout=5)
    assert len(collector.cycle()) == 2

    _FakeAPI.routes["/providers"] = (200, "not json at all", "application/json")
    records = collector.cycle()
    assert [r["kind"] for r in records] == ["catalog", "balance"], \
        "a bad catalog must not drop the providers we already had"


# ---------------------------------------------------------------- adapters


@pytest.mark.parametrize("shape,payload_value", list(SHAPES.items()))
def test_adapter_recognises_every_captured_shape(shape, payload_value):
    body, expected = payload_value
    adapted = m.adapt_payload(json.loads(body))
    assert adapted is not None, f"{shape} not recognised"
    assert adapted.shape == shape
    assert adapted.value == pytest.approx(expected)


def test_empty_object_is_a_third_state_never_zero():
    """`{}` arrived 20 times on HTTP 200 in the window, across 11 providers.

    Reading it as 0 would fabricate a total balance collapse and a critical
    alert, which is the single most expensive parsing mistake available here.
    """
    reading = m.read_sample(_rec("brightdata", 0, body="{}"))
    assert reading.state == m.STATE_SCHEMA_MISS
    assert reading.value is None
    assert m.adapt_payload({}) is None


def test_html_gateway_page_is_unparseable_not_a_crash():
    """Every 504 in the window returned an HTML error page, not JSON."""
    reading = m.read_sample(_rec("tremendous", 0, body=HTML_504, http=504, latency=3107.0))
    assert reading.state == m.STATE_UNPARSEABLE
    assert reading.value is None


@pytest.mark.parametrize("http,body", [
    (429, '{"error":"rate limited"}'),
    (500, '{"error":"upstream 500"}'),
    (503, '{"error":"upstream 503"}'),
])
def test_error_envelope_is_http_error(http, body):
    reading = m.read_sample(_rec("findymail", 0, body=body, http=http))
    assert reading.state == m.STATE_HTTP_ERROR
    assert reading.value is None


def test_transport_failure_is_its_own_state():
    record = _rec("openai", 0)
    record["http"] = None
    record.pop("body")
    record["error"] = "ConnectTimeout: timed out"
    reading = m.read_sample(record)
    assert reading.state == m.STATE_TRANSPORT_ERROR
    assert reading.value is None


def test_unknown_shape_degrades_to_schema_miss():
    """A shape nobody has seen must not be guessed at, and must not crash."""
    reading = m.read_sample(_rec("newvendor", 0, body='{"wallet_pennies":123,"v":2}'))
    assert reading.state == m.STATE_SCHEMA_MISS
    assert reading.value is None


def test_adapter_rejects_booleans_and_non_finite():
    assert m.adapt_payload({"balance": True}) is None
    assert m.adapt_payload({"gbp": "1992.17"}) is None


# ---------------------------------------------------------------- time


def test_iso_always_carries_an_explicit_z():
    rendered = m.iso(T0)
    assert rendered.endswith("Z")
    assert m.parse_ts(rendered) == T0


def test_iso_refuses_to_emit_a_naive_timestamp():
    with pytest.raises(ValueError):
        m.iso(datetime(2026, 8, 23, 16, 13, 26))


def test_parse_rejects_naive_source_data():
    with pytest.raises(ValueError):
        m.parse_ts("2026-08-23T16:13:26.775")


def test_non_utc_offsets_are_preserved_as_instants():
    """The work is graded across timezones; +05:00 local must not shift the instant."""
    assert m.parse_ts("2026-08-23T21:13:26+05:00") == m.parse_ts("2026-08-23T16:13:26Z")


# ---------------------------------------------------------------- estimator


def _topup_series(jump_at, count=60, start=8342.0, jump=1994.0, per_poll=0.5):
    """The real `findymail` shape: steady decline with one top-up inside it."""
    points, value = [], start
    for i in range(count):
        if i == jump_at:
            value += jump
        value -= per_poll
        points.append((i * 30.0, value))
    return points


def test_a_first_last_burn_rate_is_fiction_when_a_top_up_lands_inside_it():
    """The measured case: `findymail` reads +3623 credits/h on a naive estimate."""
    points = _topup_series(jump_at=15)
    naive = (points[-1][1] - points[0][1]) / ((points[-1][0] - points[0][0]) / 3600.0)
    assert naive > 3000, "a first/last rate reports the balance climbing"
    assert m.theil_sen(points) < 0, "Theil-Sen still sees the decline"


def test_theil_sen_alone_is_not_enough_when_the_jump_sits_mid_series():
    """An honest boundary on the estimator, asserted so nobody relies on it.

    Theil-Sen is the median of pairwise slopes, so it survives a jump only while
    fewer than half the pairs straddle it. Put the top-up at the exact midpoint
    of the window and 900 of 1770 pairs cross it - a bare majority - and the
    median flips positive. This is precisely why `estimate_burn` segments the
    series at a detected top-up instead of trusting robustness alone.
    """
    mid = m.theil_sen(_topup_series(jump_at=30))
    assert mid > 0, "documented limit: a midpoint jump does defeat raw Theil-Sen"


@pytest.mark.parametrize("jump_at", [10, 20, 30, 40, 50])
def test_the_full_estimator_survives_a_top_up_anywhere_in_the_window(jump_at):
    """Segmentation plus Theil-Sen: the answer is the burn, wherever the top-up lands."""
    readings = [
        m.Reading("findymail", T0 + timedelta(seconds=t), m.STATE_OK, value,
                  200, 110.0, "credits_package", {"package": 12000.0, "refresh": "2026-09-01"})
        for t, value in _topup_series(jump_at=jump_at)
    ]
    estimate = m.estimate_burn(readings, "credits_package")
    assert estimate.ok, estimate.reason
    # 0.5 credits per 30 s poll is 60 credits/h of real consumption.
    assert estimate.rate_per_h == pytest.approx(60.0, rel=0.25), \
        f"top-up at index {jump_at} contaminated the burn rate"


def test_theil_sen_survives_a_step_shaped_series():
    """`anthropic` is flat between batch charges, so adjacent deltas are mostly 0.

    A median of adjacent differences reports no spend at all on this shape.
    """
    points = []
    value = 39.40
    for i in range(60):
        if i % 20 == 19:
            value += 7.9
        points.append((i * 30.0, value))
    adjacent = [(b[1] - a[1]) / ((b[0] - a[0]) / 3600.0) for a, b in zip(points, points[1:])]
    assert statistics.median(adjacent) == 0.0, "adjacent-median is blind here"
    assert m.theil_sen(points) > 0, "Theil-Sen still sees the rise"


@pytest.mark.parametrize("window,hours", [
    ({"window": "trailing_24h"}, 24.0),
    ({"window": "trailing_720h"}, 720.0),
    ({"window": None}, 24.0),
    ({}, 24.0),
    ({"window": "rolling"}, 24.0),
])
def test_trailing_window_is_read_from_the_payload_not_assumed(window, hours):
    assert m.trailing_window_h(window) == hours


def test_a_trailing_cost_report_reports_the_window_average_not_its_derivative():
    """dV/dt of a trailing-window total is not a spend rate.

    If V(t) is spend over [t-24h, t] then dV/dt = r(t) - r(t-24h), which is
    zero while spending steadily and negative whenever the window rolls off
    faster than new cost lands. Displaying it read `anthropic` at 32.81 USD/h
    against an actual 81.70 USD per 24 h, and `meta_ads` at -11.39 USD/h, which
    invites the conclusion that a paid-ads account is earning money.
    """
    state = _state(provider="anthropic", pay_model="spend_report", unit="usd",
                   value=81.70)
    state.last_ok = m.Reading("anthropic", T0, m.STATE_OK, 81.70, 200, 110.0,
                              "cost_report", {"window": "trailing_24h"})
    m._project(state, T0)
    assert state.trailing_window_h == 24.0
    assert state.trailing_rate_per_h == pytest.approx(81.70 / 24)
    assert state.spend_rate_per_h == pytest.approx(3.404, abs=0.01)
    assert state.runway_h is None, "a cost report has no balance to run out"


def test_a_falling_trailing_report_never_shows_a_negative_spend_rate():
    """The window rolling off is not income."""
    state = _state(provider="meta_ads", pay_model="spend_report", unit="usd",
                   value=337.00)
    state.last_ok = m.Reading("meta_ads", T0, m.STATE_OK, 337.00, 200, 110.0,
                              "spend_report_24h", {"window": "trailing_24h"})
    # A steeply falling report: the derivative is negative...
    falling = [m.Reading("meta_ads", T0 + timedelta(seconds=30 * i), m.STATE_OK,
                         360.0 - i * 0.5, 200, 110.0, "spend_report_24h",
                         {"window": "trailing_24h"}) for i in range(40)]
    state.burn = m.estimate_burn(falling, "spend_report")
    m._project(state, T0)
    assert state.burn.rate_per_h < 0, "the derivative really is negative here"
    assert state.spend_rate_per_h > 0, "but the spend rate never is"
    assert state.spend_rate_per_h == pytest.approx(337.00 / 24, abs=0.01)


def test_a_balance_provider_still_reports_its_fitted_decline():
    state = _state(provider="brightdata", value=900.0)
    state.burn = m.Estimate(8.87, -8.87, 200, 7200.0, 0.01)
    assert state.spend_rate_per_h == pytest.approx(8.87)


def test_estimate_refuses_rather_than_guessing_from_too_few_samples():
    readings = [
        m.Reading("brightdata", T0 + timedelta(seconds=30 * i), m.STATE_OK,
                  100.0 - i, 200, 110.0, "flat_balance", {})
        for i in range(3)
    ]
    estimate = m.estimate_burn(readings, "prepaid_balance")
    assert not estimate.ok
    assert estimate.rate_per_h is None
    assert "samples" in (estimate.reason or "")


def test_burn_is_positive_for_both_depleting_and_accumulating_models():
    """A falling balance and a rising cost report both mean "spending"."""
    falling = [m.Reading("p", T0 + timedelta(seconds=30 * i), m.STATE_OK,
                         1000.0 - i, 200, 110.0, "flat_balance", {}) for i in range(40)]
    rising = [m.Reading("p", T0 + timedelta(seconds=30 * i), m.STATE_OK,
                        10.0 + i, 200, 110.0, "cost_report", {}) for i in range(40)]
    assert m.estimate_burn(falling, "prepaid_balance").rate_per_h > 0
    assert m.estimate_burn(rising, "spend_report").rate_per_h > 0


# ---------------------------------------------------------------- events


def _series(values, pay_model_extra=None, provider="findymail"):
    return [
        m.Reading(provider, T0 + timedelta(seconds=30 * i), m.STATE_OK, value,
                  200, 110.0, "credits_package", dict(pay_model_extra or {}))
        for i, value in enumerate(values)
    ]


def test_top_up_is_detected_as_an_event():
    values = [8342 - i for i in range(20)] + [10306 - i for i in range(20)]
    found = m.detect_discontinuities(_series(values), "credits_package")
    assert len(found) == 1
    _ts_found, kind, detail = found[0]
    assert kind == "top_up"
    assert detail["delta"] == pytest.approx(1964 + 19, abs=2)


def test_package_reset_is_distinguished_from_a_plain_top_up():
    extra = {"package": 12000.0, "refresh": "2026-09-01"}
    values = [400 - i for i in range(20)] + [12000 - i for i in range(20)]
    found = m.detect_discontinuities(_series(values, extra), "credits_package")
    assert [kind for _t, kind, _d in found] == ["package_reset"]


def test_a_rising_spend_report_is_never_a_top_up():
    """For a trailing cost report a rise IS the spend; calling it a top-up inverts it."""
    rising = [m.Reading("anthropic", T0 + timedelta(seconds=30 * i), m.STATE_OK,
                        39.40 + i * 0.5, 200, 110.0, "cost_report", {}) for i in range(40)]
    assert m.detect_discontinuities(rising, "spend_report") == []


def _twocaptcha_blip():
    """The real 17:26Z series: +10.00 USD held for eight polls, then handed back."""
    values = [72.66, 72.66, 72.66, 72.65, 72.65, 72.65, 72.65, 72.64, 72.64, 72.64,
              72.64, 72.63, 72.63, 72.63,
              82.63, 82.62, 82.62, 82.62, 82.62, 82.61, 82.61, 82.61,
              72.64, 72.63, 72.63, 72.63]
    return [
        m.Reading("twocaptcha", T0 + timedelta(seconds=30 * i), m.STATE_OK, value,
                  200, 110.0, "flat_balance", {"currency": "USD"})
        for i, value in enumerate(values)
    ]


def test_a_rise_that_is_handed_back_is_not_a_top_up():
    found = m.detect_discontinuities(_twocaptcha_blip(), "prepaid_balance")
    kinds = [kind for _t, kind, _d in found]
    assert kinds == ["reverted_blip"], f"expected one reverted blip, got {kinds}"
    detail = found[0][2]
    assert detail["delta"] == pytest.approx(10.0, abs=0.01)
    assert detail["held_s"] == pytest.approx(240.0, abs=1.0)
    # Slightly less comes back than went up (9.97 of 10.00) because real
    # consumption carried on underneath the blip. The matcher has to tolerate
    # that, which is why it compares within a fraction rather than exactly.
    assert 0 < detail["given_back"] < detail["delta"]
    assert detail["delta"] - detail["given_back"] < \
        m.BASELINE.blip_match_fraction * detail["delta"]


def test_a_reverted_blip_does_not_become_phantom_spend():
    """The regression this guard exists for.

    Cutting the series at the rise leaves the reversion inside the estimation
    window, which reported 133 USD/h and a 0.5 h runway for a provider actually
    burning 0.28 USD/h with roughly 250 h of runway. A false critical alert on
    the calmest provider in the estate is exactly the kind of line that teaches
    an operator to ignore the channel.
    """
    readings = _twocaptcha_blip()
    estimate = m.estimate_burn(readings, "prepaid_balance")
    assert estimate.ok, estimate.reason
    assert estimate.rate_per_h < 1.0, \
        f"phantom spend is back: {estimate.rate_per_h:.2f} USD/h"
    assert estimate.rate_per_h == pytest.approx(0.28, abs=0.35)


def test_a_reclassified_event_replaces_itself_rather_than_doubling_up(tmp_path):
    """One moment, one event, even when our reading of it improves."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    when = T0 + timedelta(minutes=13)
    assert store.add_event(when, "twocaptcha", "top_up", {"delta": 10.0})
    assert store.add_event(when, "twocaptcha", "reverted_blip", {"delta": 10.0, "held_s": 240})
    events = store.events(limit=10)
    assert len(events) == 1, f"one moment produced {len(events)} events"
    assert events[0]["kind"] == "reverted_blip", "the later classification must win"
    assert events[0]["detail"]["held_s"] == 240


def test_a_genuine_top_up_still_cuts_the_series():
    """The blip rule must not blunt the case it was carved out of."""
    values = [8342 - i for i in range(20)] + [10306 - i for i in range(20)]
    found = m.detect_discontinuities(_series(values), "credits_package")
    assert [kind for _t, kind, _d in found] == ["top_up"]


def test_a_large_one_off_charge_stays_in_the_burn_rate():
    """A fall with no matching rise is spend, not an event, and must not cut."""
    values = [1000.0 - i for i in range(15)] + [900.0 - i for i in range(15)]
    found = m.detect_discontinuities(_series(values), "credits_package")
    assert found == [], "an unmatched decline is ordinary spend"


def test_a_top_up_in_the_same_interval_as_spend_is_under_reported():
    """The documented measurement limit, asserted rather than only claimed.

    The API exposes a current value, so when a top-up and spend land between the
    same two polls we observe their sum and never the parts. A +100 top-up with
    5 spent in the same interval reads as +95. The event under-reports the
    top-up and the burn across that interval is a lower bound; nothing in the
    data can recover the true split, so the correct behaviour is to record the
    net honestly rather than to guess at the components.
    """
    true_topup, spend_in_interval = 100.0, 5.0
    values = [1000.0 - i * 0.5 for i in range(20)]
    at_jump = values[-1] + true_topup - spend_in_interval
    values += [at_jump - i * 0.5 for i in range(20)]

    found = m.detect_discontinuities(_series(values), "credits_package")
    assert len(found) == 1
    _ts_found, kind, detail = found[0]
    assert kind == "top_up"
    observed = detail["delta"]
    assert observed == pytest.approx(true_topup - spend_in_interval, abs=0.01)
    assert observed < true_topup, "the observed jump must be the net, not the top-up"
    # And the shortfall is exactly the spend we cannot see.
    assert true_topup - observed == pytest.approx(spend_in_interval, abs=0.01)


def test_a_top_up_near_the_end_does_not_contaminate_the_burn_rate():
    """A cut too recent to measure falls back to the whole series, safely.

    `latest_segment` only honours a cut when what follows is long enough to fit,
    so a top-up two minutes before the end leaves the estimate on the full
    series. That is only safe because few pairs straddle a jump near the edge --
    the same property that fails at the midpoint.
    """
    per_poll = 0.5
    values = [1000.0 - i * per_poll for i in range(56)]
    values += [values[-1] + 400.0 - per_poll * (i + 1) for i in range(4)]
    readings = _series(values)

    estimate = m.estimate_burn(readings, "credits_package")
    assert estimate.ok, estimate.reason
    # 0.5 per 30 s poll is 60 units/h of real consumption.
    assert estimate.rate_per_h == pytest.approx(60.0, rel=0.3), \
        f"a late top-up contaminated the rate: {estimate.rate_per_h}"


def _package_state(provider, remaining, package, burn, dispersion, now):
    state = _state(provider=provider, pay_model="credits_package", unit="credits",
                   value=float(remaining))
    state.package = float(package)
    state.refresh = "2026-09-01"
    state.burn = m.Estimate(burn, -burn, 400, 7200.0, dispersion)
    m._project(state, now)
    return state


def test_a_projection_must_survive_its_own_estimates_uncertainty():
    """The real discriminator, with the numbers that motivated it.

    `resend` at 16:48Z projected exhaustion on a burn of 226.6 credits/h whose
    MAD was 3.7 — the claim holds comfortably if the rate is a dispersion
    slower. `bounceban` at 18:44Z projected on 37.6/h with a MAD of 4.7 and only
    a 16.9 h margin, and the claim evaporates. Both cleared the flat
    2%-of-package threshold, so that threshold was not the thing telling them
    apart.
    """
    at = m.parse_ts("2026-08-23T18:44:34Z")

    solid = _package_state("resend", 41_233, 50_000, burn=226.6, dispersion=3.7, now=at)
    assert m.rule_package_exhaustion(solid, at) is not None, \
        "a well-supported projection must still fire"

    marginal = _package_state("bounceban", 6_749, 8_000, burn=37.6, dispersion=4.7, now=at)
    assert marginal.runway_h is not None and marginal.hours_to_refresh is not None
    assert marginal.runway_h < marginal.hours_to_refresh, \
        "the fixture must still project exhaustion on the point estimate"
    assert m.rule_package_exhaustion(marginal, at) is None, \
        "a projection that flips one dispersion slower must not fire"


def test_the_uncertainty_bound_is_the_providers_own_dispersion():
    """Not a tuned constant: a steady provider is held to a tighter bound."""
    burn = m.Estimate(100.0, -100.0, 400, 7200.0, 5.0)
    assert m.slower_by_one_dispersion(burn) == pytest.approx(95.0)
    noisy = m.Estimate(100.0, -100.0, 400, 7200.0, 60.0)
    assert m.slower_by_one_dispersion(noisy) == pytest.approx(40.0)
    # Never negative: a dispersion wider than the rate floors at zero.
    wild = m.Estimate(10.0, -10.0, 400, 7200.0, 999.0)
    assert m.slower_by_one_dispersion(wild) == 0.0


def test_a_runway_alert_also_survives_its_uncertainty():
    state = _state(provider="openrouter", value=243.99)
    state.burn = m.Estimate(5.10, -5.10, 400, 7200.0, 0.05)
    m._project(state, T0)
    assert m.rule_runway(state, T0) is not None, "a tight estimate must still fire"

    wobbly = _state(provider="openrouter", value=243.99)
    wobbly.burn = m.Estimate(5.10, -5.10, 400, 7200.0, 2.5)   # half the rate
    m._project(wobbly, T0)
    assert m.rule_runway(wobbly, T0) is None, \
        "a rate this uncertain cannot support a runway claim"


def test_a_projection_will_not_fire_off_a_freshly_cut_segment():
    """Right after a top-up there is not yet enough evidence to project from."""
    state = _state(provider="findymail", pay_model="credits_package",
                   unit="credits", value=10_000.0)
    state.package = 12_000.0
    state.refresh = "2026-09-01"
    # A segment only 400 s long: past min_span_s, nowhere near min_projection_span_s.
    state.burn = m.Estimate(500.0, -500.0, 12, 400.0, 1.0)
    m._project(state, T0)
    assert state.runway_h is not None, "a runway is still computed for display"
    assert m.rule_package_exhaustion(state, T0) is None, \
        "but nothing may be alerted from 400 s of evidence"


def test_sampling_noise_below_the_ratio_is_not_a_top_up():
    values = [1000.0 - i * 1.0 for i in range(20)]
    values[10] = values[9] + 0.001   # a rise far below the typical 1.0 decline
    found = m.detect_discontinuities(_series(values), "credits_package")
    assert found == []


# ---------------------------------------------------------------- rules


def _state(**kwargs):
    base = dict(provider="p", name="N", pay_model="prepaid_balance", unit="usd", note="")
    base.update(kwargs)
    return m.ProviderState(**base)


def test_postpaid_going_negative_is_not_an_alert_on_its_own():
    """`vastai` credit legitimately goes negative between top-ups."""
    state = _state(provider="vastai", pay_model="postpaid", value=-12.0)
    state.burn = m.Estimate(1.0, -1.0, 60, 3600.0, 0.0)
    m._project(state, T0)
    candidate = m.rule_runway(state, T0)
    assert candidate is None, "crossing zero must not alert; only the floor does"
    # ...but the configured floor still protects against a runaway.
    deep = _state(provider="vastai", pay_model="postpaid", value=-495.0)
    deep.burn = m.Estimate(1.0, -1.0, 60, 3600.0, 0.0)
    m._project(deep, T0)
    assert m.rule_runway(deep, T0) is not None


def test_a_projection_needs_a_minimum_evidence_span():
    """An 8-day projection from 5 minutes of data would not survive a skeptical read."""
    short = _state(value=10.0)
    short.burn = m.Estimate(1.0, -1.0, 12, 400.0, 0.0)
    m._project(short, T0)
    assert m.rule_runway(short, T0) is None

    long = _state(value=10.0)
    long.burn = m.Estimate(1.0, -1.0, 200, 7200.0, 0.0)
    m._project(long, T0)
    fired = m.rule_runway(long, T0)
    assert fired is not None
    assert fired.evidence["observed_span_s"] == 7200.0


def test_runway_alert_carries_actionable_evidence():
    state = _state(provider="openrouter", name="Groq", value=251.45)
    state.burn = m.Estimate(4.55, -4.55, 200, 7200.0, 0.01)
    m._project(state, T0)
    candidate = m.rule_runway(state, T0)
    assert candidate is not None
    for key in ("value", "unit", "burn_per_h", "runway_h", "depleted_at", "estimator", "samples"):
        assert key in candidate.evidence, f"missing evidence: {key}"
    assert candidate.evidence["estimator"] == "theil_sen"
    assert "openrouter" in candidate.text and "USD" in candidate.text


def test_collection_health_needs_more_than_the_worst_observed_cycle():
    """Worst measured was 4 of 15 failing at once; the pool rule must sit above it."""
    def pool(dark_count, stale_s):
        states = [_state(provider=f"p{i}") for i in range(15)]
        for state in states[:dark_count]:
            state.stale_s = stale_s
        for state in states[dark_count:]:
            state.stale_s = 0.0
        return states

    deep = m.POLICY.unavailable_alert_s + 1
    assert m.rule_collection_health(pool(4, deep), T0) is None, "4/15 is normal"
    assert m.rule_collection_health(pool(8, deep), T0) is not None, "8/15 is not"


def test_overlapping_self_healing_outages_do_not_trip_the_pool_rule():
    """MEASURED: three providers were mid-5xx-episode simultaneously at 16:22-16:24Z.

    Counting merely-amber providers here would page someone for routine
    flakiness that heals itself before anyone reads the line.
    """
    states = [_state(provider=f"p{i}") for i in range(15)]
    for state in states[:8]:
        state.stale_s = m.POLICY.stale_display_s + 1   # amber, but healing
        state.available = False
    assert m.rule_collection_health(states, T0) is None


# ------------------------------------------------------ alerting lifecycle


def test_a_single_timeout_produces_no_alert(tmp_path):
    """One 504 in an otherwise healthy series must be silent."""
    def builder(_provider, i):
        if i == 20:
            return (HTML_504, 504)
        return ('{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05), 200)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 60))
    assert _alert_lines(alerts) == []


def test_a_transient_429_burst_produces_no_alert(tmp_path):
    """MEASURED: 429 ran 1-2 consecutive cycles and never hit two providers at once."""
    def builder(_provider, i):
        if i in (10, 11, 25, 40, 41):
            return ('{"error":"rate limited"}', 429)
        return ('{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05), 200)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 60))
    assert _alert_lines(alerts) == []


def test_a_self_healing_five_minute_outage_produces_no_alert(tmp_path):
    """The longest 5xx episode measured was 22 polls (630 s) and healed itself."""
    def builder(_provider, i):
        if 20 <= i < 36:
            return ('{"error":"upstream 500"}', 500)
        return ('{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05), 200)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 80))
    assert [a["rule"] for a in _alert_lines(alerts)] == []


def test_a_sustained_outage_escalates_by_duration_not_by_cycle(tmp_path):
    """A dark provider is worth a line when it goes dark and again as it stays dark.

    130 cycles is 65 minutes of outage. One line per cycle would be 120 lines;
    one line ever would let a 12-hour outage look the same as a 16-minute one.
    The bands give a handful, each a genuine escalation.
    """
    def builder(_provider, i):
        if i < 10:
            return ('{"balance":900.00,"currency":"usd"}', 200)
        return ('{"error":"upstream 500"}', 500)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 130))
    fired = [a for a in _alert_lines(alerts) if a["rule"] == "unavailable"]
    assert 1 <= len(fired) <= 4, f"expected a handful of escalations, got {len(fired)}"
    assert fired[0]["provider"] == "brightdata"
    assert fired[0]["evidence"]["stale_s"] >= m.POLICY.unavailable_alert_s
    assert fired[0]["level"] == "warning"
    bands = [a["evidence"]["band"] for a in fired]
    assert len(bands) == len(set(bands)), f"a band was restated: {bands}"


def _runway_candidate(runway_h, key="runway:openrouter"):
    return m.Candidate(
        key=key, rule="runway", level="warning", provider="openrouter",
        text=f"openrouter reaches zero in {runway_h:.1f} h",
        evidence={"runway_h": runway_h}, rule_class=m.CLASS_POLICY,
        sustain_s=0.0,
        signature=m._signature(
            *(lambda b: (b[0], f"runway:warning:{b[1]}"))(
                m._band(runway_h, m.RUNWAY_BUCKETS_H, higher_is_worse=False))),
    )


def test_a_condition_flickering_across_its_threshold_speaks_once(tmp_path):
    """The `bounceban` case: two lines an hour apart, runway *improved* between.

    A projection sitting close to its own threshold clears and returns every few
    minutes. Wiping the announced band on clear made every return look like a
    fresh incident, so the log carried a second line whose runway had gone from
    180.4 h to 187.6 h — nothing a human would act on.
    """
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))

    for minute in range(0, 90, 5):
        when = T0 + timedelta(minutes=minute)
        # Present for two ticks, absent for one, over and over.
        if (minute // 5) % 3 == 2:
            alerter.process([], when)
        else:
            runway = 180.4 if minute < 45 else 187.6      # it gets *better*
            alerter.process([_runway_candidate(runway)], when)

    lines = _alert_lines(alerts)
    assert len(lines) == 1, \
        f"flicker across a threshold produced {len(lines)} lines: " \
        f"{[x['evidence']['runway_h'] for x in lines]}"


def test_a_recurrence_long_after_the_last_line_is_a_new_incident(tmp_path):
    """Remembering the band must not silence a genuine recurrence forever."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))

    alerter.process([_runway_candidate(50.0)], T0)
    alerter.process([_runway_candidate(50.0)], T0 + timedelta(minutes=1))
    assert len(_alert_lines(alerts)) == 1

    alerter.process([], T0 + timedelta(minutes=5))                       # resolved
    later = T0 + timedelta(seconds=m.POLICY.incident_forget_s + 600)
    alerter.process([_runway_candidate(50.0)], later)                    # returns
    alerter.process([_runway_candidate(50.0)], later + timedelta(minutes=1))

    lines = _alert_lines(alerts)
    assert len(lines) == 2, "a recurrence past the forget window is a new incident"


def test_a_recovering_condition_is_not_announced(tmp_path):
    """An anomaly easing from 20 MAD to 14 is not something anyone acts on."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    alerter.process([_runway_candidate(20.0)], T0)                            # sustain tick
    alerter.process([_runway_candidate(20.0)], T0 + timedelta(seconds=30))    # writes
    alerter.process([_runway_candidate(200.0)], T0 + timedelta(seconds=1200))  # recovered
    assert len(_alert_lines(alerts)) == 1, "recovery must not write a line"


def test_sliding_back_down_after_a_recovery_speaks_again(tmp_path):
    """Recovery lowers the stored band so a relapse is still announced."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    alerter.process([_runway_candidate(20.0)], T0)
    alerter.process([_runway_candidate(20.0)], T0 + timedelta(seconds=30))
    alerter.process([_runway_candidate(200.0)], T0 + timedelta(seconds=1200))
    alerter.process([_runway_candidate(20.0)], T0 + timedelta(seconds=2400))
    lines = _alert_lines(alerts)
    assert len(lines) == 2, f"relapse must be announced; got {len(lines)}"
    assert lines[-1]["evidence"]["runway_h"] == pytest.approx(20.0)


@pytest.mark.parametrize("worse,better,edges,higher_is_worse", [
    (20.0, 200.0, "RUNWAY_BUCKETS_H", False),    # less runway is worse
    (100.0, 5.0, "DEVIATION_BUCKETS", True),     # bigger deviation is worse
    (900.0, 10.0, "STALE_BUCKETS_MIN", True),    # longer outage is worse
])
def test_band_severity_points_the_right_way(worse, better, edges, higher_is_worse):
    edge_values = getattr(m, edges)
    worse_sev, _ = m._band(worse, edge_values, higher_is_worse=higher_is_worse)
    better_sev, _ = m._band(better, edge_values, higher_is_worse=higher_is_worse)
    assert worse_sev > better_sev, f"{edges}: {worse} should outrank {better}"


def test_drift_inside_a_band_is_not_restated(tmp_path):
    """The real second round: three of four restatements carried no new fact.

    elevenlabs 44.0 -> 42.7 h, scrapfly 134.9 -> 130.0 h and openrouter
    55.6 -> 52.1 h are all drift. Writing them again puts three lines a human
    cannot act on next to the one they must.
    """
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    start = T0

    for offset, runway in [(0, 55.563), (60, 55.0), (3660, 52.086), (7260, 49.0)]:
        alerter.process([_runway_candidate(runway)], start + timedelta(seconds=offset))

    lines = _alert_lines(alerts)
    assert len(lines) == 1, \
        f"55.6 -> 49.0 h never leaves the 48-72 h band; got {len(lines)} lines"


def test_crossing_a_band_is_announced_even_long_after_the_first_line(tmp_path):
    """resend went 182.0 -> 44.9 h in one round. That must produce a line."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    start = T0

    # The first evaluation only starts the sustain clock; the second writes.
    alerter.process([_runway_candidate(182.003)], start)
    alerter.process([_runway_candidate(182.003)], start + timedelta(seconds=60))
    alerter.process([_runway_candidate(180.0)], start + timedelta(seconds=1800))
    alerter.process([_runway_candidate(44.857)], start + timedelta(seconds=3600))

    lines = _alert_lines(alerts)
    assert len(lines) == 2, f"the 4x deterioration must be announced; got {len(lines)}"
    assert lines[0]["evidence"]["runway_h"] == pytest.approx(182.003)
    assert lines[1]["evidence"]["runway_h"] == pytest.approx(44.857)
    assert lines[1]["evidence"]["previous_band"] != lines[1]["evidence"]["band"]


def test_a_value_oscillating_across_a_band_edge_is_rate_limited(tmp_path):
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    for i in range(40):
        runway = 47.0 if i % 2 else 49.0          # straddles the 48 h edge
        alerter.process([_runway_candidate(runway)], T0 + timedelta(seconds=30 * i))
    lines = _alert_lines(alerts)
    assert len(lines) <= 3, f"oscillation produced {len(lines)} lines"


def test_a_band_change_while_suppressed_is_not_lost(tmp_path):
    """The stored signature must track the last line WRITTEN, not the last tick.

    If it tracked every evaluation, a condition drifting across a band during
    the rate-limit window would have its change silently absorbed and never
    announced.
    """
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    alerter.process([_runway_candidate(100.0)], T0)                              # sustain tick
    alerter.process([_runway_candidate(100.0)], T0 + timedelta(seconds=30))      # writes
    alerter.process([_runway_candidate(20.0)], T0 + timedelta(seconds=60))       # changed, too soon
    alerter.process([_runway_candidate(20.0)], T0 + timedelta(seconds=1200))     # now allowed
    lines = _alert_lines(alerts)
    assert len(lines) == 2, "the band change must survive the suppression window"
    assert lines[0]["evidence"]["runway_h"] == pytest.approx(100.0)
    assert lines[1]["evidence"]["runway_h"] == pytest.approx(20.0)


def _runway_band(value):
    return m._band(value, m.RUNWAY_BUCKETS_H, higher_is_worse=False)


@pytest.mark.parametrize("before,after", [
    (43.997, 42.703),    # elevenlabs drift, observed 16:48Z -> 17:49Z
    (134.89, 130.011),   # scrapfly drift
    (55.563, 52.086),    # openrouter drift
])
def test_observed_drift_pairs_share_a_band(before, after):
    """The three restatements the live log produced that carried no new fact."""
    assert _runway_band(before) == _runway_band(after)


def test_the_observed_deterioration_pair_does_not_share_a_band():
    """resend 182.0 -> 44.9 h in one round: the one line that mattered."""
    worse, _ = _runway_band(44.857)
    better, _ = _runway_band(182.003)
    assert _runway_band(182.003) != _runway_band(44.857)
    assert worse > better, "less runway must rank as more severe"


def test_a_flapping_provider_produces_one_line_per_episode_not_per_cycle(tmp_path):
    """Alternating up/down is the classic alert-storm generator.

    400 cycles is 200 minutes containing five distinct 20-minute outages. Five
    lines is the honest answer — they are five separate incidents — and the
    number that matters is that it is not 200.
    """
    def builder(_provider, i):
        if (i // 40) % 2 == 0:
            return ('{"balance":900.00,"currency":"usd"}', 200)
        return ('{"error":"upstream 500"}', 500)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 400))
    fired = [a for a in _alert_lines(alerts) if a["rule"] == "unavailable"]
    episodes = 5
    assert 0 < len(fired) <= episodes + 1, f"alert storm: {len(fired)} lines"


def test_top_ups_never_reach_alerts_jsonl(tmp_path):
    """A top-up is normal operations. It is an event and never an alert."""
    def builder(_provider, i):
        value = 8342 - i * 0.5
        if i >= 30:
            value += 1994
        return ('{"package":12000,"refresh":"2026-09-01","remaining":%d}' % int(value), 200)

    store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 80, providers=("findymail",)))
    kinds = [e["kind"] for e in store.events(limit=50)]
    assert "top_up" in kinds, "the top-up should be recorded as an event"
    assert all(a["rule"] != "top_up" for a in _alert_lines(alerts))
    assert not any("top" in a.get("text", "").lower() and a["level"] == "critical"
                   for a in _alert_lines(alerts))


def test_every_alert_line_is_one_json_object_with_an_aware_timestamp(tmp_path):
    def builder(_provider, i):
        return (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                else ('{"error":"upstream 500"}', 500))

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 140))
    raw = alerts.read_text(encoding="utf-8")
    assert raw, "expected at least one alert"
    for line in raw.splitlines():
        payload = json.loads(line)          # each physical line parses alone
        assert "ts" in payload and "text" in payload
        assert "provider" in payload
        parsed = m.parse_ts(payload["ts"])
        assert parsed.tzinfo is not None
        assert payload["ts"].endswith("Z")
        assert payload["rule_class"] in (m.CLASS_POLICY, m.CLASS_DERIVED)


def test_alert_state_and_history_survive_a_restart(tmp_path):
    """Restart must not re-fire a live alert nor lose the readings behind it."""
    def builder(_provider, i):
        return (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                else ('{"error":"upstream 500"}', 500))

    records = _cycles(builder, 140)
    raw = _write(tmp_path / "raw.jsonl", records)
    db = str(tmp_path / "monitor.sqlite")
    alerts = tmp_path / "alerts.jsonl"

    first = m.Store(db)
    m.Ingestor(first, m.Alerter(first, str(alerts)), str(raw)).replay()
    first_count = len(_alert_lines(alerts))
    first_coverage = first.coverage()
    assert first_count >= 1

    # A second process against the same database and the same log.
    second = m.Store(db)
    m.Ingestor(second, m.Alerter(second, str(alerts)), str(raw)).replay()
    assert len(_alert_lines(alerts)) == first_count, "restart re-fired a live alert"
    assert second.coverage()["samples"] == first_coverage["samples"], "history lost"
    assert second.alert_state("unavailable:brightdata") is not None


def test_replay_from_scratch_is_deterministic(tmp_path):
    """Delete the DB, replay, get the same alerts - this is what lets a threshold
    be re-evaluated against the whole window rather than only going forward."""
    def builder(_provider, i):
        return (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                else ('{"error":"upstream 500"}', 500))

    records = _cycles(builder, 140)
    runs = []
    for run in range(2):
        directory = tmp_path / f"run{run}"
        directory.mkdir()
        _store, _ingestor, alerts = _pipeline(directory, records)
        runs.append([(a["ts"], a["rule"], a["provider"]) for a in _alert_lines(alerts)])
    assert runs[0] == runs[1]
    assert runs[0], "expected the run to produce alerts at all"


# ---------------------------------------------------------------- ingestion


def test_malformed_lines_do_not_stop_ingestion(tmp_path):
    good = _cycles(lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 12)
    raw = tmp_path / "raw.jsonl"
    with open(raw, "w", encoding="utf-8") as handle:
        for index, record in enumerate(good):
            handle.write(json.dumps(record) + "\n")
            if index == 5:
                handle.write("this is not json at all\n")
                handle.write('{"ts":"2026-08-23T16:13:26Z"}\n')     # no kind
                handle.write('{"kind":"balance","provider":"x"}\n')  # no ts
                handle.write("[]\n")                                 # not an object
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    ingestor = m.Ingestor(store, m.Alerter(store, str(tmp_path / "alerts.jsonl")), str(raw))
    ingestor.replay()
    assert store.coverage()["samples"] == 12


def test_a_partial_trailing_line_is_left_for_the_next_pass(tmp_path):
    """The sampler fsyncs each line, but a read can still land mid-write."""
    records = _cycles(lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 6)
    raw = tmp_path / "raw.jsonl"
    with open(raw, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
        handle.write('{"ts":"2026-08-23T16:20:00Z","kind":"bala')  # torn write

    store = m.Store(str(tmp_path / "monitor.sqlite"))
    ingestor = m.Ingestor(store, m.Alerter(store, str(tmp_path / "alerts.jsonl")), str(raw))
    ingestor.replay()
    before = store.coverage()["samples"]

    with open(raw, "a", encoding="utf-8") as handle:
        handle.write('nce","provider":"brightdata","http":200,'
                     '"latency_ms":110,"body":"{\\"balance\\":1.0,\\"currency\\":\\"usd\\"}"}\n')
    ingestor.replay()
    assert store.coverage()["samples"] == before + 1


def test_since_scopes_derived_state_without_touching_the_raw_log(tmp_path):
    """How a clean window is produced without disturbing the capture.

    The submitted artifacts must be the product of one stable configuration
    rather than an accumulation across code versions. That is achieved by
    replaying the raw log from a marker instant with frozen code — the collector
    keeps running untouched throughout, because raw capture is independent of
    alert logic. Deriving from an append-only log rather than from memory is
    what buys this.
    """
    records = _cycles(
        lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 60)
    raw = _write(tmp_path / "raw.jsonl", records)
    digest_before = hashlib.sha256(raw.read_bytes()).hexdigest()

    marker = T0 + timedelta(seconds=30 * 30)
    store = m.Store(str(tmp_path / "clean.sqlite"))
    ingestor = m.Ingestor(store, m.Alerter(store, str(tmp_path / "clean-alerts.jsonl")),
                          str(raw), since=marker)
    ingestor.replay()

    coverage = store.coverage()
    assert coverage["samples"] > 0, "the scoped window must still contain data"
    assert m.parse_ts(coverage["first_ts"]) >= marker, \
        "no record before the marker may reach derived state"

    # Roughly half the cycles are after the marker.
    full = m.Store(str(tmp_path / "full.sqlite"))
    m.Ingestor(full, m.Alerter(full, str(tmp_path / "full-alerts.jsonl")), str(raw)).replay()
    assert coverage["samples"] < full.coverage()["samples"]

    assert hashlib.sha256(raw.read_bytes()).hexdigest() == digest_before, \
        "the raw log must not be modified"


def test_ingestion_is_idempotent_under_repeated_replay(tmp_path):
    records = _cycles(lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 20)
    store, ingestor, _alerts = _pipeline(tmp_path, records)
    first = store.coverage()["samples"]
    ingestor.store.put_state(m.Ingestor.OFFSET_KEY, "0")   # force a full re-read
    ingestor.replay()
    assert store.coverage()["samples"] == first, "replay duplicated readings"


def test_a_truncated_log_resets_the_offset(tmp_path):
    records = _cycles(lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 20)
    store, ingestor, _alerts = _pipeline(tmp_path, records)
    ingestor.store.put_state(m.Ingestor.OFFSET_KEY, "999999999")
    assert ingestor._load_offset() == 0


# ---------------------------------------------------------------- snapshot


def _healthy_pipeline(tmp_path, cycles=80):
    bodies = {
        "brightdata": lambda i: '{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05),
        "findymail": lambda i: '{"package":12000,"refresh":"2026-09-01","remaining":%d}' % (10306 - i),
        "vastai": lambda i: '{"credit":%.2f,"unit":"usd"}' % (49.66 - i * 0.05),
        "anthropic": lambda i: '{"object":"cost_report","amount_cents":%d,"window":"trailing_24h"}' % (3940 + i * 5),
    }
    records = _cycles(lambda p, i: (bodies[p](i), 200), cycles,
                      providers=tuple(bodies))
    return _pipeline(tmp_path, records)


@pytest.mark.parametrize("unit,fungible", [
    ("usd", True), ("USD", True), ("gbp", True), ("eur", True),
    ("credits", False), ("characters", False), ("", False), (None, False),
])
def test_only_currencies_are_fungible_across_vendors(unit, fungible):
    assert m.is_fungible_unit(unit) is fungible


def test_credits_are_never_summed_across_providers(tmp_path):
    """The regression this exists for: a headline number that was not a quantity.

    `elevenlabs` credits are TTS characters, `resend` credits are emails,
    `scrapfly` credits are API calls. The dashboard was adding 850,199 of one to
    40,076 of another and printing the result in the one-glance summary. Two USD
    balances add up; two "credits" balances share a label, not a unit.
    """
    bodies = {
        "findymail": lambda i: '{"package":12000,"refresh":"2026-09-01","remaining":%d}' % (10306 - i),
        "bounceban": lambda i: '{"package":8000,"refresh":"2026-09-01","remaining":%d}' % (6800 - i * 2),
    }
    records = _cycles(lambda p, i: (bodies[p](i), 200), 80, providers=tuple(bodies))
    store, _ingestor, _alerts = _pipeline(tmp_path, records)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))

    credits = snap["groups"]["credits_package/credits"]
    assert credits["fungible"] is False
    assert credits["value"] is None, "a credits group must publish no total"
    assert credits["burn_per_h"] is None, "a credits group must publish no summed burn"
    assert credits["providers"] == 2
    # The comparable quantity is time, and it is still reported.
    assert credits["soonest"] is not None
    assert credits["soonest"]["provider"] in bodies

    html = m.render_dashboard(snap)
    assert "not summed" in html
    combined = 10306 + 6800
    assert f"{combined:,}" not in html, "a summed credit total reached the page"


def test_currency_balances_are_still_summed(tmp_path):
    """The fix must not over-correct: dollars really are additive."""
    bodies = {
        "brightdata": lambda i: '{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05),
        "openai": lambda i: '{"balance":%.2f,"currency":"usd"}' % (600 - i * 0.04),
    }
    records = _cycles(lambda p, i: (bodies[p](i), 200), 80, providers=tuple(bodies))
    store, _ingestor, _alerts = _pipeline(tmp_path, records)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))
    usd = snap["groups"]["prepaid_balance/usd"]
    assert usd["fungible"] is True
    assert usd["value"] == pytest.approx(900 - 79 * 0.05 + 600 - 79 * 0.04, abs=0.5)
    assert usd["burn_per_h"] > 0


def test_dispersion_is_measured_over_the_population_the_estimate_medians():
    """MAD must describe the same slopes Theil-Sen takes a median of.

    It was computed over *adjacent* differences while the field documented
    pairwise. Adjacent deltas are dominated by per-poll quantisation, so the
    MAD came out far wider than the pairwise spread and the anomaly threshold
    inherited that inflation.
    """
    points = [(i * 30.0, 1000.0 - i * 0.5) for i in range(60)]
    pairwise = m.pairwise_slopes(points)
    adjacent = [(b[1] - a[1]) / ((b[0] - a[0]) / 3600.0) for a, b in zip(points, points[1:])]
    assert len(pairwise) > len(adjacent), "pairwise draws from all pairs, not neighbours"

    readings = [
        m.Reading("p", T0 + timedelta(seconds=t), m.STATE_OK, v, 200, 110.0, "flat_balance", {})
        for t, v in points
    ]
    estimate = m.estimate_burn(readings, "prepaid_balance")
    assert estimate.dispersion == pytest.approx(m.mad(pairwise))
    assert estimate.rate_per_h == pytest.approx(-statistics.median(pairwise))


def test_dispersion_widens_when_the_rate_itself_varies():
    steady = [(i * 30.0, 1000.0 - i * 0.5) for i in range(60)]
    # Rate changes halfway: the slope population genuinely spreads.
    def two_rate(i):
        return 1000.0 - (i * 0.5 if i < 30 else 15.0 + (i - 30) * 2.0)
    varying = [(i * 30.0, two_rate(i)) for i in range(60)]
    assert m.mad(m.pairwise_slopes(steady)) == 0.0
    assert m.mad(m.pairwise_slopes(varying)) > 0.0


def test_a_minority_of_spikes_leaves_the_dispersion_at_zero():
    """MAD is supposed to ignore a minority of outliers - that is the point.

    A consequence worth pinning: for the steadiest providers the dispersion is
    exactly 0, so the anomaly scale floor is not a defensive nicety, it is the
    only thing standing between the rule and a division that makes every
    deviation infinite.
    """
    spiky = [(i * 30.0, 1000.0 - i * 0.5 + (12.0 if i % 7 == 0 else 0.0)) for i in range(60)]
    assert m.mad(m.pairwise_slopes(spiky)) == 0.0
    assert m.BASELINE.anomaly_scale_floor_fraction > 0, "the floor carries this case"


def test_the_anomaly_scale_never_collapses_to_zero():
    state = _state(provider="twocaptcha", value=72.0)
    state.burn = m.Estimate(0.28, -0.28, 200, 7200.0, 0.0)      # MAD exactly 0
    state.recent_burn = m.Estimate(0.30, -0.30, 60, 1800.0, 0.0)
    # A 7% wobble against a zero MAD must not read as an infinite deviation.
    assert m.rule_burn_anomaly(state, T0) is None


def test_a_handler_error_is_logged_and_not_leaked_to_the_client(tmp_path, capfd, monkeypatch):
    """A 500 seen from outside must leave a trace inside.

    The external verification run caught a 500 with nothing whatsoever in the
    container log, because the handler returned the exception text to the caller
    and wrote nothing to stderr. That is backwards on a public endpoint: the
    operator gets silence and the internet gets internal type and path names.
    """
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    store, ingestor, _alerts = _pipeline(tmp_path, _cycles(
        lambda _p, i: ('{"balance":900.00,"currency":"usd"}', 200), 6))

    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic failure with /secret/internal/path")

    monkeypatch.setattr(m, "snapshot", boom)
    m.Handler.store = store
    m.Handler.ingestor = ingestor
    m.Handler.alerts_path = str(tmp_path / "alerts.jsonl")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10)
            raise AssertionError("expected a 500")
        except urllib.error.HTTPError as err:
            assert err.code == 500
            body = err.read().decode()
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert "internal error" in body
    assert "/secret/internal/path" not in body, "internals leaked to the client"
    assert "RuntimeError" not in body
    err_output = capfd.readouterr().err
    assert "RuntimeError" in err_output, "the operator got no trace of the failure"
    assert "/secret/internal/path" in err_output, "the log should carry the detail"


def test_alerts_endpoint_serves_the_path_selected_by_the_cli(tmp_path):
    """`--alerts elsewhere.jsonl` wrote one file and served another, silently."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    store, ingestor, alerts = _pipeline(tmp_path, _cycles(
        lambda _p, i: ('{"balance":900.00,"currency":"usd"}', 200), 6))
    custom = tmp_path / "somewhere-else.jsonl"
    custom.write_text('{"ts":"2026-08-23T16:00:00.000Z","text":"from the custom path"}\n',
                      encoding="utf-8")

    m.Handler.store = store
    m.Handler.ingestor = ingestor
    m.Handler.alerts_path = str(custom)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/alerts.jsonl", timeout=10) as r:
            body = r.read().decode()
        assert "from the custom path" in body, "endpoint served the wrong file"
        assert body != alerts.read_text(encoding="utf-8") if alerts.exists() else True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_aggregation_never_crosses_a_pay_model_or_a_currency(tmp_path):
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))
    keys = set(snap["groups"])
    assert keys == {"prepaid_balance/usd", "credits_package/credits",
                    "postpaid/usd", "spend_report/usd"}
    for key, group in snap["groups"].items():
        assert key == f"{group['pay_model']}/{group['unit']}"
    # USD balance and USD trailing spend are different things and stay apart.
    assert snap["groups"]["prepaid_balance/usd"]["value"] != \
        snap["groups"]["spend_report/usd"]["value"]


def _condition_pipeline(tmp_path, cycles, name="raw.jsonl"):
    """A provider that goes dark, so a condition moves through its lifecycle."""
    def builder(_provider, i):
        return (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                else ('{"error":"upstream 500"}', 500))
    return _pipeline(tmp_path, _cycles(builder, cycles), name=name)


def test_a_condition_inside_its_sustain_window_reads_as_pending(tmp_path):
    """Nothing has been written, so nothing may claim an incident was raised."""
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    candidate = m.Candidate(
        key="runway:openrouter", rule="runway", level="warning", provider="openrouter",
        text="openrouter reaches zero in 50 h", evidence={"runway_h": 50.0},
        rule_class=m.CLASS_POLICY, sustain_s=300.0, signature="02|runway:warning:lt72")

    # First tick starts the sustain clock; 60 s in, it is still holding.
    alerter.process([candidate], T0)
    alerter.process([candidate], T0 + timedelta(seconds=60))
    status = m.condition_status(store, candidate, T0 + timedelta(seconds=60))
    assert status["status"] == "pending"
    assert status["sustain_remaining_s"] == pytest.approx(240.0, abs=1)
    assert status["last_fired"] is None
    assert _alert_lines(alerts) == [], "pending must mean nothing was written"

    # Past the sustain period, a line is written and it reads as firing.
    alerter.process([candidate], T0 + timedelta(seconds=400))
    status = m.condition_status(store, candidate, T0 + timedelta(seconds=400))
    assert status["status"] == "firing"
    assert status["sustain_remaining_s"] == 0.0
    assert len(_alert_lines(alerts)) == 1


def test_a_recurrence_reads_as_pending_until_its_own_line_is_written(tmp_path):
    """The UI must not inherit a `firing` from a previous episode.

    Full sequence: appears, fires, disappears, reappears, stays pending through
    the sustain period, fires again. Reading `last_fired` without comparing it
    to `active_since` showed the second episode as firing from the moment it
    reappeared, while alerts.jsonl contained no line for it — the dashboard
    claiming an incident had been raised that nobody had been told about.
    """
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerts = tmp_path / "alerts.jsonl"
    alerter = m.Alerter(store, str(alerts))
    candidate = m.Candidate(
        key="runway:openrouter", rule="runway", level="warning", provider="openrouter",
        text="openrouter reaches zero in 50 h", evidence={"runway_h": 50.0},
        rule_class=m.CLASS_POLICY, sustain_s=300.0, signature="02|runway:warning:lt72")

    def status_at(when):
        return m.condition_status(store, candidate, when)

    # 1. appears — pending, sustain running
    alerter.process([candidate], T0)
    assert status_at(T0)["status"] == "pending"

    # 2. sustain elapses and it fires
    fired_at = T0 + timedelta(seconds=400)
    alerter.process([candidate], fired_at)
    assert status_at(fired_at)["status"] == "firing"
    assert len(_alert_lines(alerts)) == 1

    # 3. disappears
    gone = T0 + timedelta(seconds=700)
    alerter.process([], gone)

    # 4. reappears, well past the forget window so it is a genuine new incident
    back = gone + timedelta(seconds=m.POLICY.incident_forget_s + 600)
    alerter.process([candidate], back)
    reappeared = status_at(back)
    assert reappeared["status"] == "pending", \
        "a new episode must not inherit firing from the previous one"
    assert reappeared["last_fired_this_episode"] is False
    assert len(_alert_lines(alerts)) == 1, "and no line has been written for it yet"

    # 5. still pending part-way through the sustain period
    midway = back + timedelta(seconds=120)
    alerter.process([candidate], midway)
    assert status_at(midway)["status"] == "pending"
    assert status_at(midway)["sustain_remaining_s"] > 0

    # 6. fires again once sustained, and now reads as firing
    refired = back + timedelta(seconds=400)
    alerter.process([candidate], refired)
    assert len(_alert_lines(alerts)) == 2, "the new episode must produce its own line"
    final = status_at(refired)
    assert final["status"] == "firing"
    assert final["last_fired_this_episode"] is True


def test_the_dashboard_and_the_alerter_agree_about_firing(tmp_path):
    """Whatever the UI calls firing must be backed by a line in the file."""
    store, _ingestor, alerts = _condition_pipeline(tmp_path, 140)
    at = T0 + timedelta(seconds=140 * 30)
    snap = m.snapshot(store, at)
    written = _alert_lines(alerts)
    keys_with_lines = {(x["rule"], x["provider"]) for x in written}
    for condition in snap["conditions"]:
        if condition["status"] == "firing":
            assert (condition["rule"], condition["provider"]) in keys_with_lines, \
                f"UI says firing but no line exists: {condition['rule']}/{condition['provider']}"


def test_a_deteriorating_condition_is_flagged_before_the_line_is_written(tmp_path):
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    alerter = m.Alerter(store, str(tmp_path / "alerts.jsonl"))
    calm = _runway_candidate(100.0)
    alerter.process([calm], T0)
    alerter.process([calm], T0 + timedelta(seconds=60))
    assert m.condition_status(store, calm, T0 + timedelta(seconds=60))["deteriorated"] is False

    worse = _runway_candidate(20.0)
    status = m.condition_status(store, worse, T0 + timedelta(seconds=90))
    assert status["status"] == "firing", "a line already exists for this key"
    assert status["deteriorated"] is True, "the band worsened since that line"


def test_the_dashboard_separates_pending_from_written(tmp_path):
    store, _ingestor, _alerts = _condition_pipeline(tmp_path, 40)
    html = m.render_dashboard(m.snapshot(store, T0 + timedelta(seconds=40 * 30)))
    assert "Conditions holding now" in html
    assert "Lines written to alerts.jsonl" in html
    assert "nobody has been told" in html


def test_a_condition_reads_as_firing_once_a_line_exists(tmp_path):
    store, _ingestor, alerts = _condition_pipeline(tmp_path, 140)
    snap = m.snapshot(store, T0 + timedelta(seconds=140 * 30))
    fired = [c for c in snap["conditions"] if c["status"] == "firing"]
    assert fired, "a written line must show as firing"
    assert _alert_lines(alerts), "and the file must actually contain it"
    assert fired[0]["last_fired"] is not None
    html = m.render_dashboard(snap)
    assert "Conditions holding now" in html
    assert "Lines written to alerts.jsonl" in html


def test_a_same_band_active_condition_is_not_marked_deteriorated(tmp_path):
    store, _ingestor, _alerts = _condition_pipeline(tmp_path, 140)
    snap = m.snapshot(store, T0 + timedelta(seconds=140 * 30))
    firing = [c for c in snap["conditions"] if c["status"] == "firing"]
    assert firing and not any(c["deteriorated"] for c in firing)


def test_a_recovered_condition_leaves_the_live_list_but_not_the_record(tmp_path):
    """The file is a record; it must not rewrite itself when things improve."""
    def builder(_provider, i):
        if i < 5 or i >= 130:
            return ('{"balance":900.00,"currency":"usd"}', 200)
        return ('{"error":"upstream 500"}', 500)

    store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 160))
    written = _alert_lines(alerts)
    assert written, "the outage should have produced a line while it lasted"
    snap = m.snapshot(store, T0 + timedelta(seconds=160 * 30))
    assert not [c for c in snap["conditions"] if c["rule"] == "unavailable"], \
        "a recovered condition must drop out of the live list"
    assert len(_alert_lines(alerts)) == len(written), "the record must not shrink"


def test_pending_conditions_rank_below_firing_ones(tmp_path):
    pending = _state(provider="p_pending", value=1.0)
    pending.runway_h = 2.0
    pending.alerts = [{"level": "critical", "rule": "runway", "status": "pending"}]
    firing = _state(provider="a_firing", value=1.0)
    firing.runway_h = 50.0
    firing.alerts = [{"level": "warning", "rule": "runway", "status": "firing"}]
    calm = _state(provider="b_calm", value=100.0)
    calm.runway_h = 900.0
    ordered = sorted([pending, firing, calm], key=m.risk_key)
    assert [s.provider for s in ordered] == ["a_firing", "p_pending", "b_calm"]


def test_risk_sort_puts_alerting_providers_first_not_alphabetical(tmp_path):
    calm = _state(provider="zzz_calm", value=100.0)
    calm.runway_h = 900.0
    firing = _state(provider="aaa_firing", value=1.0)
    firing.runway_h = 2.0
    firing.alerts = [{"level": "critical", "rule": "runway"}]
    stale = _state(provider="mmm_stale")
    stale.available = False
    stale.stale_s = 4000.0
    ordered = sorted([calm, firing, stale], key=m.risk_key)
    assert [s.provider for s in ordered] == ["aaa_firing", "mmm_stale", "zzz_calm"]


def test_spend_report_providers_get_no_fabricated_runway(tmp_path):
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))
    anthropic = next(s for s in snap["providers"] if s.provider == "anthropic")
    assert anthropic.runway_h is None, "a trailing cost report has no balance to run out"
    assert anthropic.burn.rate_per_h > 0, "but it does have a measurable spend rate"


def test_dashboard_renders_and_states_its_limits(tmp_path):
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path)
    html = m.render_dashboard(m.snapshot(store, T0 + timedelta(seconds=80 * 30)))
    assert html.startswith("<!doctype html>")
    assert "Theil" in html, "the estimator should be named on the page"
    assert "operational_policy" in html and "data_derived" in html
    assert "Known measurement limit" in html, "the measurement limit must be stated"
    assert "lower bound" in html, "burn must be labelled a lower bound across top-ups"
    for provider in ("brightdata", "findymail", "vastai", "anthropic"):
        assert provider in html


def test_alert_evidence_is_rendered_complete_not_clipped(tmp_path):
    """A panel whose job is carrying evidence must not print malformed JSON.

    Clipping a json.dumps to a character budget cut it mid-token and rendered
    things like `"threshold_h": 72.0, "` on screen.
    """
    def builder(_provider, i):
        return (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                else ('{"error":"upstream 500"}', 500))

    store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 140))
    fired = _alert_lines(alerts)
    assert fired, "expected an alert to render"
    html = m.render_dashboard(m.snapshot(store, T0 + timedelta(seconds=140 * 30)))
    for key in ("stale_s", "consecutive_failures", "tolerance_s", "band"):
        assert key in html, f"evidence field {key} missing from the page"
    assert '", "' not in html.split("PROVIDERS")[-1], "clipped JSON fragment on the page"


def test_text_report_renders_for_every_group_kind(tmp_path):
    """`--once` is a delivered entry point and must not crash on its own output.

    It did: making the credits total None to stop summing non-fungible units
    left `text_report` formatting None with `:,.2f`. The dashboard and snapshot
    tests all passed, because none of them exercised this renderer.
    """
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))
    report = m.text_report(snap)
    assert "not summed (unit is vendor-specific)" in report
    assert "prepaid_balance/usd" in report and "credits_package/credits" in report
    for line in report.splitlines():
        assert "None" not in line, f"unrendered None in the report: {line!r}"


def test_once_mode_runs_end_to_end(tmp_path):
    """Exercise the CLI path itself, not just the functions underneath it."""
    records = _cycles(
        lambda p, i: ({
            "brightdata": '{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05),
            "findymail": '{"package":12000,"refresh":"2026-09-01","remaining":%d}' % (10306 - i),
        }[p], 200), 40, providers=("brightdata", "findymail"))
    raw = _write(tmp_path / "raw.jsonl", records)
    code = m.main([
        "--once", "--raw", str(raw),
        "--db", str(tmp_path / "monitor.sqlite"),
        "--alerts", str(tmp_path / "alerts.jsonl"),
    ])
    assert code == 0


def test_snapshot_is_json_serialisable(tmp_path):
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path)
    snap = m.snapshot(store, T0 + timedelta(seconds=80 * 30))
    encoded = json.dumps(m._jsonable(snap), default=str)
    assert '"provider"' in encoded


# ---------------------------------------------------------------- health


def test_healthz_is_unhealthy_when_every_provider_is_stale(tmp_path):
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path, cycles=40)
    catalog = store.catalog()

    fresh_at = T0 + timedelta(seconds=40 * 30)
    fresh = m.build_state(store, fresh_at, catalog)
    assert all(s.available for s in fresh)

    # Same process, same data, much later: the numbers on screen are now stale.
    later = m.build_state(store, fresh_at + timedelta(hours=3), catalog)
    assert not any(s.available for s in later), "stale data must not read as fresh"


def test_state_as_of_an_instant_does_not_read_the_future(tmp_path):
    """Evaluating a past moment must not use readings taken after it.

    Live replay never exposed this: there the newest record and the evaluation
    instant advance together, so nothing later exists yet. Against a fully
    populated database, `--as-of` and `--audit` were both reading forward — the
    audit re-derived openrouter at 18:03:32Z as 236.03 when the raw reading at
    that instant was 243.99.
    """
    records = _cycles(
        lambda _p, i: ('{"balance":%.2f,"currency":"usd"}' % (900 - i), 200), 60)
    store, _ingestor, _alerts = _pipeline(tmp_path, records)

    midpoint = T0 + timedelta(seconds=30 * 30)
    bounded = store.readings_since("brightdata", T0, until=midpoint)
    assert bounded, "expected readings up to the midpoint"
    assert all(r.ts <= midpoint for r in bounded)
    assert len(bounded) < len(store.readings_since("brightdata", T0))

    state = {s.provider: s for s in m.build_state(store, midpoint, store.catalog())}["brightdata"]
    expected = [r.value for r in bounded if r.state == m.STATE_OK][-1]
    end_of_log = [r.value for r in store.readings_since("brightdata", T0)
                  if r.state == m.STATE_OK][-1]
    assert state.value == expected, "state must reflect the instant, not the end of the log"
    assert expected != end_of_log, "the fixture must actually distinguish the two"


def test_the_audit_reconciles_every_line_it_is_given(tmp_path):
    """The audit must grade the file it was handed, not one its replay extended."""
    records = _cycles(
        lambda _p, i: (('{"balance":900.00,"currency":"usd"}', 200) if i < 5
                       else ('{"error":"upstream 500"}', 500)), 140)
    store, _ingestor, alerts = _pipeline(tmp_path, records)
    captured = m.read_alert_lines(str(alerts))
    assert captured, "expected the pipeline to have written lines"

    report, unreconciled = m.audit_alerts(store, captured)
    assert unreconciled == 0, report
    assert f"of {len(captured)}" in report, "audit must grade exactly what it was given"
    for line in captured:
        assert line["ts"] in report


def test_healthz_returns_503_when_every_provider_is_stale(tmp_path):
    """The case a liveness probe cannot see: process up, every number wrong."""
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path, cycles=40)
    fresh_at = T0 + timedelta(seconds=40 * 30)

    payload, code = m.healthz(store, True, now=fresh_at)
    assert code == 200 and payload["status"] == "ok"
    assert payload["providers_fresh"] == payload["providers_total"] == 4
    assert payload["reason"] is None

    payload, code = m.healthz(store, True, now=fresh_at + timedelta(hours=3))
    assert code == 503, "a live process serving stale numbers must report unhealthy"
    assert payload["status"] == "unhealthy"
    assert payload["providers_fresh"] == 0
    assert len(payload["providers_stale"]) == 4
    assert payload["reason"] == "every provider's data is stale"


def test_healthz_stays_ok_while_one_provider_still_reports(tmp_path):
    """Partial staleness is a per-provider alert, not a collection failure."""
    store, _ingestor, _alerts = _healthy_pipeline(tmp_path, cycles=40)
    catalog = store.catalog()
    fresh_at = T0 + timedelta(seconds=40 * 30)
    # One provider keeps reporting well past the others.
    store.add_readings([m.Reading("brightdata", fresh_at + timedelta(hours=3),
                                  m.STATE_OK, 500.0, 200, 110.0, "flat_balance", {})])
    payload, code = m.healthz(store, True, now=fresh_at + timedelta(hours=3))
    assert code == 200, "one live provider means collection is still working"
    assert payload["providers_fresh"] == 1
    assert len(payload["providers_stale"]) == len(catalog) - 1


def test_healthz_reports_unhealthy_with_an_empty_catalog(tmp_path):
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    assert m.build_state(store, T0, store.catalog()) == []
    payload, code = m.healthz(store, False, now=T0)
    assert code == 503
    assert payload["reason"] == "no providers in catalog"


# ---------------------------------------------------------------- policy


def test_thresholds_sit_where_the_measurements_say_they_should():
    """Guards against a well-meaning edit that silently reintroduces alert spam."""
    longest_transient_s = 60.0     # 2 cycles of 504/429
    longest_self_healing_s = 630.0  # 22 consecutive failed polls, findymail 18:08Z
    assert m.POLICY.unavailable_alert_s > longest_self_healing_s
    assert m.POLICY.unavailable_alert_s >= 10 * longest_transient_s
    assert m.POLICY.stale_display_s < m.POLICY.unavailable_alert_s, \
        "freshness must become visible before it becomes an alert"
    worst_observed_pool_failure = 4 / 15
    assert m.POLICY.pool_error_fraction > worst_observed_pool_failure


def test_policy_can_be_retuned_without_touching_rule_code(monkeypatch):
    """Operational policy is config, so a different employer answer is a one-line change."""
    monkeypatch.setattr(m, "POLICY", replace(m.POLICY, runway_warning_h=1.0))
    state = _state(value=10.0)
    state.burn = m.Estimate(1.0, -1.0, 200, 7200.0, 0.0)
    m._project(state, T0)
    assert state.runway_h == pytest.approx(10.0)
    assert m.rule_runway(state, T0) is None, "10 h runway is fine under a 1 h warning policy"
