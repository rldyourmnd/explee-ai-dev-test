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
