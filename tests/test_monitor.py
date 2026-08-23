"""Tests for the spend monitor.

The cases worth testing hardest are the ones where a plausible implementation
silently produces fiction rather than failing: `{}` read as a zero balance, a
top-up read as spend, a first/last burn rate across a hole, a flapping provider
read as two hundred incidents. Each of those has a test that asserts the
fabricated answer is *not* produced, using payloads and numbers taken from the
captured window rather than invented ones.
"""
import importlib.util
import json
import statistics
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "monitor", ROOT / "task1-spend-observability" / "monitor.py")
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
    """The longest 5xx episode measured was 16 cycles (480 s) and healed itself."""
    def builder(_provider, i):
        if 20 <= i < 36:
            return ('{"error":"upstream 500"}', 500)
        return ('{"balance":%.2f,"currency":"usd"}' % (900 - i * 0.05), 200)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 80))
    assert [a["rule"] for a in _alert_lines(alerts)] == []


def test_a_sustained_outage_alerts_exactly_once(tmp_path):
    """A provider dark far longer than anything measured is worth exactly one line."""
    def builder(_provider, i):
        if i < 10:
            return ('{"balance":900.00,"currency":"usd"}', 200)
        return ('{"error":"upstream 500"}', 500)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 130))
    fired = [a for a in _alert_lines(alerts) if a["rule"] == "unavailable"]
    assert len(fired) == 1, f"expected one line, got {len(fired)}"
    assert fired[0]["provider"] == "brightdata"
    assert fired[0]["evidence"]["stale_s"] >= m.POLICY.unavailable_alert_s
    assert fired[0]["level"] == "warning"


def test_a_flapping_provider_produces_one_line_not_hundreds(tmp_path):
    """Alternating up/down for an hour is the classic alert-storm generator."""
    def builder(_provider, i):
        if (i // 40) % 2 == 0:
            return ('{"balance":900.00,"currency":"usd"}', 200)
        return ('{"error":"upstream 500"}', 500)

    _store, _ingestor, alerts = _pipeline(tmp_path, _cycles(builder, 400))
    fired = [a for a in _alert_lines(alerts) if a["rule"] == "unavailable"]
    assert 0 < len(fired) <= 3, f"cooldown failed: {len(fired)} lines"


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


def test_healthz_reports_unhealthy_with_an_empty_catalog(tmp_path):
    store = m.Store(str(tmp_path / "monitor.sqlite"))
    states = m.build_state(store, T0, store.catalog())
    assert states == []


# ---------------------------------------------------------------- policy


def test_thresholds_sit_where_the_measurements_say_they_should():
    """Guards against a well-meaning edit that silently reintroduces alert spam."""
    longest_transient_s = 60.0     # 2 cycles of 504/429
    longest_self_healing_s = 480.0  # 16 cycles of upstream 500
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
