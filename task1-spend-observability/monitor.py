# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Spend monitor: collection, derivation, alerting and dashboard in one file.

This is the whole system. `monitor.py --poll` collects from the API, derives
state, alerts and serves, needing nothing but a Python runtime. `raw_sampler.py`
in this directory is not the other half of it: it is the twenty-line bootstrap
that went live at T0 because the task needs six hours of observation and the API
has no history endpoint, so capture had to begin before there was anything to
capture with.

Both modes reach the same code. Collection only ever appends raw records, and
everything downstream reads them back through one parser, so the live path and
the replay path cannot drift apart. Records come either from `--poll` or from an
existing `raw_samples.jsonl`; the deployed instance uses the latter, because the
API should see one client and the log should have one writer.

Deriving from an append-only log rather than from memory buys three things: the
dashboard shows history from T0 rather than from process start, any threshold
change can be recomputed against the whole window by deleting the SQLite file
and replaying, and in the deployed configuration the API still sees exactly one
client.

Every number below is either MEASURED (derived from the captured window and
recomputable from it) or an ASSUMPTION (operational policy the employer never
specified). The two are labelled separately in `POLICY` and surfaced separately
on the dashboard, because pretending a guessed SLA is a measurement would be the
same class of error as summing USD and credits.

Stdlib only, on purpose: the deploy target needs a Python runtime and nothing
else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from typing import Any, Callable, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.environ.get("MONITOR_RAW", os.path.join(HERE, "data", "raw_samples.jsonl"))
DB_PATH = os.environ.get("MONITOR_DB", os.path.join(HERE, "data", "monitor.sqlite"))
ALERTS_PATH = os.environ.get("MONITOR_ALERTS", os.path.join(HERE, "alerts.jsonl"))
BIND = os.environ.get("MONITOR_BIND", "127.0.0.1")
PORT = int(os.environ.get("MONITOR_PORT", "8770"))

CYCLE_S = 30.0  # MEASURED: sampler cadence, median inter-sample delta is 30.0 s

# Standalone collection (`--poll`). Off by default: the deployed instance derives
# from the log the bootstrap sampler has been writing since T0, and a second
# poller would put a second client in front of the API and a second writer into
# the same file.
API_BASE = os.environ.get("MONITOR_API",
                          "https://jobs.explee.com/ai-native-developer/test/api")
POLL_INTERVAL_S = float(os.environ.get("MONITOR_POLL_INTERVAL", "30"))
POLL_TIMEOUT_S = float(os.environ.get("MONITOR_POLL_TIMEOUT", "10"))


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """Operational policy — ASSUMPTIONS, not derivable from the captured data.

    No SLA, no balance floor and no runway lead time were ever supplied. These
    are therefore choices, stated here so a reader can disagree with a number
    without having to read the rule that consumes it. Where a measurement can
    *bound* a choice, the bound is quoted in the comment.
    """

    # Freshness shown on the dashboard and used by /healthz. Tight on purpose:
    # the operator should see a provider going quiet long before anyone is
    # woken about it. MEASURED: 10 consecutive missed polls.
    stale_display_s: float = 300.0

    # When a dark provider becomes an alert. MEASURED bounds, in cycles of 30 s:
    #   transient 504/429      1-2 cycles   (30-60 s)
    #   self-healing 5xx runs  10-22 polls (300-630 s), 15 episodes in under 3 h
    #                          across 10 of 15 providers, every one self-healing
    # A 5-8 minute gap that heals itself is not actionable - nobody can do
    # anything about it and it is over before they read the line. 900 s sits
    # 15x above the longest transient and ~1.9x above the longest self-healing
    # episode observed, so an alert means "longer than any outage we actually
    # measured", not "the API is flaky again". This is the single number most
    # worth disagreeing with, which is why the bounds are quoted next to it.
    unavailable_alert_s: float = 900.0

    # How long a threshold crossing must hold before it is worth a line. Applies
    # to the estimate-driven rules, where one noisy evaluation should not fire.
    estimate_sustain_s: float = 300.0

    # Runway lead time. Pure policy: how much warning a human wants.
    runway_critical_h: float = 24.0
    runway_warning_h: float = 72.0

    # Postpaid credit may legitimately go negative between top-ups, so zero is
    # not the interesting boundary and crossing it is not an alert. No credit
    # limit was ever supplied; this stands in for one.
    postpaid_floor: float = -500.0

    # Collection-wide health. MEASURED bound: the worst single cycle in the
    # observed window had 4 of 15 providers failing (26.7%). 50% sustained for
    # 180 s is well clear of normal pool noise and indicates the collector or
    # the upstream API, not one vendor.
    pool_error_fraction: float = 0.50
    pool_error_sustain_s: float = 180.0

    # Alert hygiene. A line is written when a condition starts and when it
    # materially worsens - never merely because time passed.
    #
    # MEASURED: with a plain one-hour cooldown the second round of firing
    # restated elevenlabs 44.0 -> 42.7 h, scrapfly 134.9 -> 130.0 h and
    # openrouter 55.6 -> 52.1 h, none of which a human can act on differently,
    # while resend went 182.0 -> 44.9 h in the same round - a fourfold
    # deterioration sitting in a block of lines that looked identical. Burying
    # the one line that mattered among three that did not is how an alert
    # channel gets ignored.
    #
    # Materiality is judged by which bucket the headline number falls in, so
    # drift inside a bucket is silent and crossing one is not. This floor only
    # bounds pathological oscillation across a bucket edge.
    refire_min_gap_s: float = 600.0

    # How long a resolved condition is remembered. A condition that oscillates
    # around its own threshold clears and returns repeatedly; forgetting the
    # band it last announced would make every return look like a new incident.
    # MEASURED: `bounceban` sits just barely inside package exhaustion -- 180 h
    # of runway against 196 h to refresh -- so its projection flickers across
    # the line, and it produced two lines an hour apart whose runway had
    # *improved* from 180.4 h to 187.6 h. Nothing had happened worth a second
    # line.
    #
    # After this long, a recurrence is a genuinely new incident and says so.
    incident_forget_s: float = 6 * 3600.0

    # A credits package resets on its refresh date. Projecting a package to
    # exhaust before then is only worth saying if the shortfall is material.
    package_shortfall_fraction: float = 0.02


@dataclass(frozen=True)
class Baseline:
    """Data-derived estimator parameters.

    These govern how the observed window is turned into a rate; they are not
    thresholds about what is acceptable.
    """

    # Theil-Sen needs a real span to mean anything. MEASURED: at 30 s cadence a
    # 10-minute window holds ~20 points even for the providers that spent a
    # third of the window returning 500.
    min_samples: int = 8
    min_span_s: float = 300.0

    # Evidence required before a *projection* is allowed to wake anyone. A
    # runway or a projected-at-refresh figure extrapolates the observed slope
    # far past the window it was measured in - projecting to a 2026-09-01
    # package refresh from 5 minutes of data is a 2000x extrapolation, and an
    # alert built on it would not survive a skeptical read. Every projection
    # alert also carries its extrapolation_ratio so the reader can judge it.
    min_projection_span_s: float = 1800.0

    # Full-window baseline vs a short recent window, compared for anomalies.
    recent_window_s: float = 1800.0
    baseline_window_s: float = 21600.0

    # Theil-Sen is O(n^2) in pairs; subsample evenly above this many points.
    max_slope_points: int = 120

    # Anomaly sensitivity in MADs. sigma ~ 1.4826*MAD, so 6 MAD ~ 4 sigma.
    anomaly_k: float = 6.0
    # MAD is exactly 0 for the steadiest providers, which would make every
    # deviation infinite. Floor the scale at a fraction of the baseline rate.
    anomaly_scale_floor_fraction: float = 0.10

    # Distinguishing a top-up from sampling noise. MEASURED: the two positive
    # jumps in the observed window were 1994x and 7.5x the median per-poll
    # decline; nothing else was positive at all. 3x leaves a wide margin on
    # both sides of that gap.
    topup_min_ratio: float = 3.0
    # A credits package reset returns `remaining` to ~`package`.
    reset_fraction_of_package: float = 0.90

    # A rise that is handed back is not a top-up. MEASURED: `twocaptcha`
    # reported +10.00 USD for exactly eight polls at 17:26Z and then returned to
    # its previous value. The observed blip lasted 4 minutes; 15 minutes leaves
    # room for a longer one without being wide enough to pair a real top-up with
    # unrelated later spend.
    blip_window_s: float = 900.0
    blip_match_fraction: float = 0.10


POLICY = Policy()
BASELINE = Baseline()

# Pay models whose value falls as money is spent, versus those whose value
# rises because they report cumulative spend rather than a balance.
DEPLETING = {"prepaid_balance", "credits_package", "postpaid"}
ACCUMULATING = {"spend_report"}

TRAILING_WINDOW = re.compile(r"trailing_(\d+)h")
DEFAULT_TRAILING_H = 24.0


def trailing_window_h(extra: dict[str, Any]) -> float:
    """Length of the window a spend report covers, from the payload itself.

    `anthropic` states it (`"window": "trailing_24h"`), so it is read rather
    than assumed; 24 h is the fallback for a report that omits it.
    """
    match = TRAILING_WINDOW.search(str(extra.get("window") or ""))
    if match:
        hours = float(match.group(1))
        if hours > 0:
            return hours
    return DEFAULT_TRAILING_H


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------


def parse_ts(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp, always returning an aware UTC datetime."""
    text = raw.strip()
    if text.endswith(("z", "Z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"naive timestamp in source data: {raw!r}")
    return parsed.astimezone(timezone.utc)


def iso(moment: datetime) -> str:
    """Render an aware datetime as ISO-8601 with an explicit Z."""
    if moment.tzinfo is None:
        raise ValueError("refusing to emit a naive timestamp")
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Schema adapters
# --------------------------------------------------------------------------
#
# Dispatch is on the *shape that actually came back*, never on the provider ID.
# The catalog proves IDs are opaque (`brightdata` reports as "Oxylabs",
# `meta_ads` as "Google Ads"), so keying an adapter off an ID would encode a
# vendor guess that the data explicitly contradicts.

CURRENCY_KEY = re.compile(r"^[a-z]{3}$")


def is_fungible_unit(unit: str | None) -> bool:
    """Whether two providers' balances in this unit may be added together.

    A currency is fungible across vendors: a dollar of `openai` credit and a
    dollar of `brightdata` credit are both a dollar. A vendor quota is not.
    The catalog calls six different things "credits" - TTS characters, emails,
    API calls, email lookups, verifications - and they share a label, not a
    unit.
    """
    return bool(unit) and bool(CURRENCY_KEY.match(str(unit).strip().lower()))

# States a single poll can be in. `schema_miss` is deliberately distinct from
# both a value and an HTTP error: MEASURED, `{}` arrived 20 times on HTTP 200,
# spread over 11 of 15 providers, never twice in a row. Reading it as 0 would
# fabricate a balance collapse.
STATE_OK = "ok"
STATE_SCHEMA_MISS = "schema_miss"
STATE_HTTP_ERROR = "http_error"
STATE_UNPARSEABLE = "unparseable"
STATE_TRANSPORT_ERROR = "transport_error"


@dataclass(frozen=True)
class Adapted:
    shape: str
    value: float
    extra: dict[str, Any]


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def adapt_payload(payload: Any) -> Adapted | None:
    """Normalise a decoded provider body into a single comparable reading.

    Returns None when the payload carries no value, which covers `{}`, an
    `{"error": ...}` envelope, and any shape this monitor has never seen.
    """
    if not isinstance(payload, dict) or not payload:
        return None
    if "error" in payload:
        return None

    # {"balance": 947.3, "currency": "usd"}
    balance = _num(payload.get("balance"))
    if balance is not None:
        return Adapted("flat_balance", balance, {"currency": payload.get("currency")})

    # {"credit": 49.66, "unit": "usd"} - postpaid, may be negative
    credit = _num(payload.get("credit"))
    if credit is not None:
        return Adapted("postpaid_credit", credit, {"currency": payload.get("unit")})

    # {"package": 12000, "refresh": "2026-09-01", "remaining": 10306}
    remaining = _num(payload.get("remaining"))
    if remaining is not None:
        return Adapted(
            "credits_package",
            remaining,
            {"package": _num(payload.get("package")), "refresh": payload.get("refresh")},
        )

    # {"object": "cost_report", "amount_cents": 3940, "window": "trailing_24h"}
    cents = _num(payload.get("amount_cents"))
    if cents is not None:
        return Adapted(
            "cost_report",
            cents / 100.0,
            {"window": payload.get("window"), "object": payload.get("object")},
        )

    # {"spend_usd_24h": 347.72, "spend_usd_30d": 10431.67}
    spend_24h = _num(payload.get("spend_usd_24h"))
    if spend_24h is not None:
        return Adapted(
            "spend_report_24h",
            spend_24h,
            {"spend_30d": _num(payload.get("spend_usd_30d")), "window": "trailing_24h"},
        )

    # {"ok": true, "data": {"wallet": {"amount": 304.38, "ccy": "usd"}}}
    data = payload.get("data")
    if isinstance(data, dict):
        wallet = data.get("wallet")
        if isinstance(wallet, dict):
            amount = _num(wallet.get("amount"))
            if amount is not None:
                return Adapted("nested_wallet", amount, {"currency": wallet.get("ccy")})

    # {"gbp": 1992.17} - a bare currency key, no envelope at all
    if len(payload) == 1:
        (key, value), = payload.items()
        amount = _num(value)
        if amount is not None and CURRENCY_KEY.match(str(key)):
            return Adapted("bare_currency_key", amount, {"currency": str(key)})

    return None


@dataclass(frozen=True)
class Reading:
    provider: str
    ts: datetime
    state: str
    value: float | None
    http: int | None
    latency_ms: float | None
    shape: str | None
    extra: dict[str, Any]


def read_sample(record: dict[str, Any]) -> Reading | None:
    """Turn one raw sampler record into a Reading, or None if it is not a poll.

    Returns None rather than raising for anything unusable. A malformed line in
    an append-only log is data about the log, not a reason to take the monitor
    down - and a record with no parseable timestamp cannot be placed on the
    series at all, so there is nothing useful to do with it.
    """
    provider = record.get("provider")
    if record.get("kind") != "balance" or not provider:
        return None
    raw_ts = record.get("ts")
    if not isinstance(raw_ts, str):
        return None
    try:
        ts = parse_ts(raw_ts)
    except ValueError:
        return None
    http = record.get("http")
    latency = record.get("latency_ms")

    if http is None:
        # The sampler never reached the server at all.
        return Reading(provider, ts, STATE_TRANSPORT_ERROR, None, None, latency, None,
                       {"error": record.get("error")})

    body = record.get("body")
    if not isinstance(body, str):
        return Reading(provider, ts, STATE_UNPARSEABLE, None, http, latency, None, {})

    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        # MEASURED: every 504 in the window returned an HTML gateway page, not
        # JSON. Unparseable is a transport-class failure, not a schema problem.
        return Reading(provider, ts, STATE_UNPARSEABLE, None, http, latency, None,
                       {"body_prefix": body[:80]})

    if http != 200:
        detail = payload.get("error") if isinstance(payload, dict) else None
        return Reading(provider, ts, STATE_HTTP_ERROR, None, http, latency, None,
                       {"error": detail})

    adapted = adapt_payload(payload)
    if adapted is None:
        return Reading(provider, ts, STATE_SCHEMA_MISS, None, http, latency, None,
                       {"keys": sorted(payload)[:8] if isinstance(payload, dict) else None})

    return Reading(provider, ts, STATE_OK, adapted.value, http, latency,
                   adapted.shape, adapted.extra)


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog (
    provider   TEXT PRIMARY KEY,
    name       TEXT,
    pay_model  TEXT,
    unit       TEXT,
    endpoint   TEXT,
    note       TEXT,
    seen_ts    TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    provider   TEXT NOT NULL,
    ts         TEXT NOT NULL,
    state      TEXT NOT NULL,
    value      REAL,
    http       INTEGER,
    latency_ms REAL,
    shape      TEXT,
    extra      TEXT,
    PRIMARY KEY (provider, ts)
);
CREATE INDEX IF NOT EXISTS readings_ts ON readings (ts);
CREATE TABLE IF NOT EXISTS events (
    id       TEXT PRIMARY KEY,
    ts       TEXT NOT NULL,
    provider TEXT NOT NULL,
    kind     TEXT NOT NULL,
    detail   TEXT
);
CREATE TABLE IF NOT EXISTS alert_state (
    key           TEXT PRIMARY KEY,
    active_since  TEXT,
    last_fired    TEXT,
    signature     TEXT
);
CREATE TABLE IF NOT EXISTS fired_alerts (
    id      TEXT PRIMARY KEY,
    ts      TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_state (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


class Store:
    """SQLite (WAL) persistence for derived state.

    Every write is idempotent under replay: readings are keyed on
    (provider, ts), events and fired alerts on a content hash. That makes
    "delete the DB and replay the log" a supported operation rather than a
    duplicate-generating one, which is what lets a threshold be re-evaluated
    against the whole window.
    """

    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        with self.conn() as conn:
            conn.executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        existing = getattr(self._local, "conn", None)
        if existing is None:
            existing = sqlite3.connect(self.path, timeout=30.0)
            existing.row_factory = sqlite3.Row
            existing.execute("PRAGMA journal_mode=WAL")
            existing.execute("PRAGMA synchronous=NORMAL")
            existing.execute("PRAGMA busy_timeout=30000")
            self._local.conn = existing
        return existing

    # -- catalog ---------------------------------------------------------
    def upsert_catalog(self, entries: Sequence[dict[str, Any]], ts: datetime) -> None:
        with self._write_lock, self.conn() as conn:
            conn.executemany(
                "INSERT INTO catalog (provider,name,pay_model,unit,endpoint,note,seen_ts) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET "
                "name=excluded.name, pay_model=excluded.pay_model, unit=excluded.unit, "
                "endpoint=excluded.endpoint, note=excluded.note, seen_ts=excluded.seen_ts",
                [
                    (e.get("provider"), e.get("name"), e.get("pay_model"), e.get("unit"),
                     e.get("endpoint"), e.get("note"), iso(ts))
                    for e in entries
                    if isinstance(e, dict) and e.get("provider")
                ],
            )

    def catalog(self) -> dict[str, dict[str, Any]]:
        rows = self.conn().execute("SELECT * FROM catalog ORDER BY provider").fetchall()
        return {r["provider"]: dict(r) for r in rows}

    # -- readings --------------------------------------------------------
    def add_readings(self, readings: Sequence[Reading]) -> None:
        if not readings:
            return
        with self._write_lock, self.conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO readings "
                "(provider,ts,state,value,http,latency_ms,shape,extra) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (r.provider, iso(r.ts), r.state, r.value, r.http, r.latency_ms,
                     r.shape, json.dumps(r.extra, ensure_ascii=False))
                    for r in readings
                ],
            )

    def readings_since(self, provider: str, since: datetime,
                       until: datetime | None = None) -> list[Reading]:
        """Readings in [since, until]. `until` bounds the window at an instant.

        Without an upper bound, evaluating a *historical* moment against a fully
        populated database silently uses readings from after that moment. Live
        replay never noticed, because there the newest record and the evaluation
        instant advance together and nothing later exists yet. Any after-the-fact
        analysis - `--as-of`, `--audit` - was reading the future.
        """
        if until is None:
            rows = self.conn().execute(
                "SELECT * FROM readings WHERE provider=? AND ts>=? ORDER BY ts",
                (provider, iso(since)),
            ).fetchall()
        else:
            rows = self.conn().execute(
                "SELECT * FROM readings WHERE provider=? AND ts>=? AND ts<=? ORDER BY ts",
                (provider, iso(since), iso(until)),
            ).fetchall()
        return [self._row_to_reading(r) for r in rows]

    def recent_readings(self, provider: str, limit: int) -> list[Reading]:
        rows = self.conn().execute(
            "SELECT * FROM readings WHERE provider=? ORDER BY ts DESC LIMIT ?",
            (provider, limit),
        ).fetchall()
        return [self._row_to_reading(r) for r in reversed(rows)]

    @staticmethod
    def _row_to_reading(row: sqlite3.Row) -> Reading:
        return Reading(
            provider=row["provider"],
            ts=parse_ts(row["ts"]),
            state=row["state"],
            value=row["value"],
            http=row["http"],
            latency_ms=row["latency_ms"],
            shape=row["shape"],
            extra=json.loads(row["extra"] or "{}"),
        )

    def coverage(self) -> dict[str, Any]:
        row = self.conn().execute(
            "SELECT COUNT(*) n, MIN(ts) first_ts, MAX(ts) last_ts FROM readings"
        ).fetchone()
        ok = self.conn().execute(
            "SELECT COUNT(*) n FROM readings WHERE state=?", (STATE_OK,)
        ).fetchone()["n"]
        by_state = {
            r["state"]: r["n"]
            for r in self.conn().execute(
                "SELECT state, COUNT(*) n FROM readings GROUP BY state"
            ).fetchall()
        }
        return {
            "samples": row["n"],
            "ok_samples": ok,
            "first_ts": row["first_ts"],
            "last_ts": row["last_ts"],
            "by_state": by_state,
        }

    # -- events ----------------------------------------------------------
    def add_event(self, ts: datetime, provider: str, kind: str, detail: dict[str, Any]) -> bool:
        """Record one discontinuity, keyed on when it happened, not what we called it.

        The classification of a moment can legitimately change as more of the
        series arrives: at 17:26Z `twocaptcha` +10.00 was indistinguishable
        from a top-up, and only the reversion four minutes later revealed it as
        a blip. Keying on (provider, kind, ts) stored both readings and showed a
        human two contradictory events for one moment. Keying on (provider, ts)
        lets the better-informed classification replace the earlier one.
        """
        ident = hashlib.sha256(f"{provider}|{iso(ts)}".encode()).hexdigest()[:16]
        with self._write_lock, self.conn() as conn:
            cur = conn.execute(
                "INSERT INTO events (id,ts,provider,kind,detail) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, detail=excluded.detail "
                "WHERE kind IS NOT excluded.kind",
                (ident, iso(ts), provider, kind, json.dumps(detail, ensure_ascii=False)),
            )
        return cur.rowcount > 0

    def events(self, limit: int = 40, provider: str | None = None) -> list[dict[str, Any]]:
        if provider:
            rows = self.conn().execute(
                "SELECT * FROM events WHERE provider=? ORDER BY ts DESC LIMIT ?",
                (provider, limit),
            ).fetchall()
        else:
            rows = self.conn().execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"] or "{}")
            out.append(d)
        return out

    # -- alert state -----------------------------------------------------
    def alert_state(self, key: str) -> dict[str, Any] | None:
        row = self.conn().execute("SELECT * FROM alert_state WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def set_alert_state(self, key: str, active_since: datetime | None,
                        last_fired: str | None, signature: str | None) -> None:
        with self._write_lock, self.conn() as conn:
            conn.execute(
                "INSERT INTO alert_state (key,active_since,last_fired,signature) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET active_since=excluded.active_since, "
                "last_fired=excluded.last_fired, signature=excluded.signature",
                (key, iso(active_since) if active_since else None, last_fired, signature),
            )

    def record_fired(self, ident: str, ts: datetime, payload: dict[str, Any]) -> bool:
        with self._write_lock, self.conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO fired_alerts (id,ts,payload) VALUES (?,?,?)",
                (ident, iso(ts), json.dumps(payload, ensure_ascii=False)),
            )
        return cur.rowcount > 0

    def fired_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn().execute(
            "SELECT payload FROM fired_alerts ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # -- ingest bookkeeping ----------------------------------------------
    def get_state(self, key: str) -> str | None:
        row = self.conn().execute("SELECT v FROM ingest_state WHERE k=?", (key,)).fetchone()
        return row["v"] if row else None

    def put_state(self, key: str, value: str) -> None:
        with self._write_lock, self.conn() as conn:
            conn.execute(
                "INSERT INTO ingest_state (k,v) VALUES (?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, value),
            )


# --------------------------------------------------------------------------
# Estimation
# --------------------------------------------------------------------------


def _subsample(points: Sequence[tuple[float, float]], cap: int) -> Sequence[tuple[float, float]]:
    if len(points) <= cap:
        return points
    step = len(points) / cap
    picked = [points[min(len(points) - 1, int(i * step))] for i in range(cap)]
    if picked[-1] != points[-1]:
        picked[-1] = points[-1]
    return picked


def pairwise_slopes(points: Sequence[tuple[float, float]],
                    min_dt_s: float = 60.0) -> list[float]:
    """Every pairwise slope in units per hour, from an evenly subsampled series.

    This is the population Theil-Sen takes a median of, so it is also the
    population whose spread describes the uncertainty of that median. Measuring
    dispersion over *adjacent* differences instead - which is what this used to
    do while the docstring claimed otherwise - samples a much noisier quantity:
    adjacent deltas are dominated by per-poll quantisation, so the MAD came out
    far too wide and the anomaly threshold with it.
    """
    sample = _subsample(points, BASELINE.max_slope_points)
    slopes: list[float] = []
    for i in range(len(sample)):
        t_i, v_i = sample[i]
        for j in range(i + 1, len(sample)):
            t_j, v_j = sample[j]
            dt = t_j - t_i
            if dt >= min_dt_s:
                slopes.append((v_j - v_i) / (dt / 3600.0))
    return slopes


def theil_sen(points: Sequence[tuple[float, float]],
              min_dt_s: float = 60.0) -> float | None:
    """Median of pairwise slopes, in value-units per hour.

    Chosen over a first/last difference because the captured window contains
    both top-ups and multi-minute holes torn by 500/504 responses. MEASURED:
    for `findymail` the first/last estimate reads +3623 credits/h - a +1994
    top-up divided by the window - while Theil-Sen reads -55 credits/h, which
    is the rate the provider was actually consuming at.

    Also chosen over a median of *adjacent* differences, which collapses on the
    step-shaped series: `anthropic` is flat between batch charges, so half its
    adjacent deltas are zero and the median is meaningless.
    """
    slopes = pairwise_slopes(points, min_dt_s)
    return statistics.median(slopes) if slopes else None


def mad(values: Sequence[float]) -> float:
    """Median absolute deviation."""
    if len(values) < 2:
        return 0.0
    centre = statistics.median(values)
    return statistics.median([abs(v - centre) for v in values])


@dataclass
class Segment:
    """A run of readings uninterrupted by a top-up or package reset."""

    points: list[tuple[datetime, float]] = field(default_factory=list)

    @property
    def span_s(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return (self.points[-1][0] - self.points[0][0]).total_seconds()


CUT_KINDS = ("top_up", "package_reset")


def detect_discontinuities(readings: Sequence[Reading], pay_model: str
                           ) -> list[tuple[datetime, str, dict[str, Any]]]:
    """Find top-ups, package resets and reverted blips in a value series.

    Only depleting pay models can be topped up. For a `spend_report` the value
    is cumulative trailing cost, so a rise *is* the spend and calling it a
    top-up would invert the meaning entirely.

    A rise that is handed back is not a top-up. MEASURED: `twocaptcha` returned
    +10.00 USD for exactly eight polls at 17:26Z and then went back to 72.63.
    Cutting the series at that rise left the reversion sitting inside the
    estimation window, which turned it into 133 USD/h of phantom spend and a
    0.5 h runway against a true 0.28 USD/h and ~250 h. Reverted blips are
    therefore classified apart and never used to cut the series - see
    `CUT_KINDS`.
    """
    if pay_model not in DEPLETING:
        return []
    values = [(r.ts, r.value, r.extra) for r in readings if r.state == STATE_OK and r.value is not None]
    if len(values) < 3:
        return []

    deltas = [b[1] - a[1] for a, b in zip(values, values[1:])]
    declines = [abs(d) for d in deltas if d < 0]
    typical = statistics.median(declines) if declines else 0.0

    # Every move clearing the provider's own noise floor, in both directions.
    # Falls matter here even though a fall is never an event on its own,
    # because a fall is what identifies a rise as having been given back.
    moves: list[tuple[datetime, datetime, float, float, float, dict[str, Any]]] = []
    for (t_prev, v_prev, _), (t_now, v_now, extra) in zip(values, values[1:]):
        delta = v_now - v_prev
        if delta == 0:
            continue
        if typical > 0 and abs(delta) < BASELINE.topup_min_ratio * typical:
            continue
        moves.append((t_prev, t_now, v_prev, v_now, delta, extra))

    # Pair each rise with a later fall of matching size inside the blip window.
    reverted: dict[int, tuple[datetime, float]] = {}
    claimed: set[int] = set()
    for i, rise in enumerate(moves):
        if rise[4] <= 0:
            continue
        for j in range(i + 1, len(moves)):
            fall = moves[j]
            if j in claimed or fall[4] >= 0:
                continue
            if (fall[1] - rise[1]).total_seconds() > BASELINE.blip_window_s:
                break
            if abs(abs(fall[4]) - rise[4]) <= BASELINE.blip_match_fraction * rise[4]:
                reverted[i] = (fall[1], abs(fall[4]))
                claimed.add(j)
                break

    found: list[tuple[datetime, str, dict[str, Any]]] = []
    for index, (t_prev, t_now, v_prev, v_now, delta, extra) in enumerate(moves):
        detail = {
            "from": round(v_prev, 6),
            "to": round(v_now, 6),
            "delta": round(delta, 6),
            "gap_s": round((t_now - t_prev).total_seconds(), 1),
            "typical_decline_per_poll": round(typical, 6),
            "ratio_to_typical": round(abs(delta) / typical, 1) if typical else None,
            "refresh": extra.get("refresh"),
        }
        if index in reverted:
            reverted_at, given_back = reverted[index]
            found.append((t_now, "reverted_blip", dict(
                detail,
                reverted_at=iso(reverted_at),
                given_back=round(given_back, 6),
                held_s=round((reverted_at - t_now).total_seconds(), 1),
            )))
            continue
        if delta < 0:
            # An ordinary large charge is spend. It belongs in the rate, not in
            # the event log, and must not cut the series.
            continue
        package = extra.get("package")
        kind = "package_reset" if (
            package and v_now >= BASELINE.reset_fraction_of_package * package) else "top_up"
        found.append((t_now, kind, detail))
    return found


def latest_segment(readings: Sequence[Reading], pay_model: str,
                   cuts: Sequence[tuple[datetime, str, dict[str, Any]]] | None = None) -> Segment:
    """Values since the most recent top-up or reset.

    Theil-Sen already survives a single large jump, but segmenting means the
    reported burn describes conditions *now* rather than an average across a
    balance that has since been refilled.
    """
    ok = [(r.ts, r.value) for r in readings if r.state == STATE_OK and r.value is not None]
    if not ok:
        return Segment([])
    found = detect_discontinuities(readings, pay_model) if cuts is None else cuts
    cut_points = [ts for ts, kind, _detail in found if kind in CUT_KINDS]
    if cut_points:
        last_cut = max(cut_points)
        after = [(ts, v) for ts, v in ok if ts >= last_cut]
        # Only honour the cut if what follows is still long enough to measure;
        # otherwise a top-up 30 seconds ago would erase the burn rate entirely.
        if len(after) >= BASELINE.min_samples and \
                (after[-1][0] - after[0][0]).total_seconds() >= BASELINE.min_span_s:
            return Segment(after)
    return Segment(ok)


@dataclass
class Estimate:
    """Burn estimate for one provider, or an explicit statement that there is none."""

    rate_per_h: float | None          # positive = spending, in the provider's own unit
    slope_per_h: float | None         # signed rate of change of the raw value
    samples: int
    span_s: float
    dispersion: float | None          # MAD of pairwise slopes, same units
    reason: str | None = None         # why there is no estimate

    @property
    def ok(self) -> bool:
        return self.rate_per_h is not None


def estimate_burn(readings: Sequence[Reading], pay_model: str,
                  window_s: float | None = None,
                  cuts: Sequence[tuple[datetime, str, dict[str, Any]]] | None = None) -> Estimate:
    segment = latest_segment(readings, pay_model, cuts)
    points = segment.points
    if window_s is not None and points:
        cutoff = points[-1][0] - timedelta(seconds=window_s)
        points = [p for p in points if p[0] >= cutoff]

    if len(points) < BASELINE.min_samples:
        return Estimate(None, None, len(points), 0.0, None,
                        f"only {len(points)} usable samples, need {BASELINE.min_samples}")
    span = (points[-1][0] - points[0][0]).total_seconds()
    if span < BASELINE.min_span_s:
        return Estimate(None, None, len(points), span, None,
                        f"span {span:.0f}s below the {BASELINE.min_span_s:.0f}s minimum")

    origin = points[0][0]
    numeric = [((t - origin).total_seconds(), v) for t, v in points]
    # One pass: the median of these slopes is the estimate, the MAD of the same
    # population is its dispersion. Computing the two over different samples is
    # what the previous version did, and it made the anomaly scale meaningless.
    slopes = pairwise_slopes(numeric)
    if not slopes:
        return Estimate(None, None, len(points), span, None, "no pair far enough apart to fit")
    slope = statistics.median(slopes)
    spread = mad(slopes)

    # A depleting balance falls as it is spent; a spend report rises. Both are
    # reported as a positive "spend per hour".
    rate = -slope if pay_model in DEPLETING else slope
    return Estimate(rate, slope, len(points), span, spread)


# --------------------------------------------------------------------------
# Provider state
# --------------------------------------------------------------------------


@dataclass
class ProviderState:
    provider: str
    name: str
    pay_model: str
    unit: str
    note: str

    last_reading: Reading | None = None
    last_ok: Reading | None = None
    value: float | None = None
    package: float | None = None
    refresh: str | None = None
    spend_30d: float | None = None

    burn: Estimate | None = None
    recent_burn: Estimate | None = None

    # Spend reports only. A trailing-window total is not a balance and its
    # derivative is not a spend rate: if V(t) is spend over [t-24h, t] then
    # dV/dt = r(t) - r(t-24h), which is zero while spending steadily. The
    # defensible rate is V / window, and the derivative is kept separately as
    # an acceleration signal.
    trailing_rate_per_h: float | None = None
    trailing_window_h: float | None = None

    stale_s: float | None = None
    available: bool = True
    unavailable_since: datetime | None = None
    consecutive_failures: int = 0

    runway_h: float | None = None
    depleted_at: datetime | None = None
    projection_at_refresh: float | None = None
    hours_to_refresh: float | None = None
    extrapolation_ratio: float | None = None

    # The window's readings, carried so the callers that need them do not each
    # re-query. Excluded from the JSON view: it is working state, not a fact
    # about the provider.
    readings: list[Reading] = field(default_factory=list, repr=False)
    cuts: list[tuple[datetime, str, dict[str, Any]]] = field(default_factory=list, repr=False)

    spark: list[float] = field(default_factory=list)
    spark_ts: list[datetime] = field(default_factory=list)
    window_span_s: float = 0.0
    ok_samples: int = 0
    total_samples: int = 0
    alerts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def depleting(self) -> bool:
        return self.pay_model in DEPLETING

    @property
    def spend_rate_per_h(self) -> float | None:
        """The number to put in front of a human as "burn", per pay model.

        For a balance this is the fitted rate of decline. For a trailing spend
        report it is the window average, never the derivative - showing dV/dt
        for `anthropic` read 32.81 USD/h against an actual 81.70 USD per 24 h,
        an order of magnitude out and in the wrong direction whenever the
        window happened to be rolling off.
        """
        if self.pay_model in ACCUMULATING:
            return self.trailing_rate_per_h
        return self.burn.rate_per_h if self.burn and self.burn.ok else None

    @property
    def health_pct(self) -> float | None:
        if not self.total_samples:
            return None
        return 100.0 * self.ok_samples / self.total_samples


def state_from_readings(provider: str, meta: dict[str, Any],
                        readings: Sequence[Reading], now: datetime) -> ProviderState:
    """Derive one provider's state from a supplied series.

    Split out from `build_state` so the same derivation can be run against a
    series that did not come from the store — which is what lets the audit
    recompute an alert with a top-up removed and check the alert survives it.
    """
    state = ProviderState(
        provider=provider,
        name=meta.get("name") or provider,
        pay_model=meta.get("pay_model") or "unknown",
        unit=meta.get("unit") or "unknown",
        note=meta.get("note") or "",
    )
    state.total_samples = len(readings)
    oks = [r for r in readings if r.state == STATE_OK]
    state.ok_samples = len(oks)

    if readings:
        state.last_reading = readings[-1]
        state.window_span_s = (readings[-1].ts - readings[0].ts).total_seconds()
    if oks:
        state.last_ok = oks[-1]
        state.value = oks[-1].value
        state.package = oks[-1].extra.get("package")
        state.refresh = oks[-1].extra.get("refresh")
        state.spend_30d = oks[-1].extra.get("spend_30d")
        state.stale_s = (now - oks[-1].ts).total_seconds()
        state.spark = [r.value for r in oks if r.value is not None][-120:]
        state.spark_ts = [r.ts for r in oks if r.value is not None][-120:]

    # Availability: how long since the last reading that carried a value.
    # `schema_miss` counts as a failure to observe, because it is exactly
    # that - but it is counted separately from an HTTP error everywhere it
    # is displayed.
    trailing = 0
    for reading in reversed(readings):
        if reading.state == STATE_OK:
            break
        trailing += 1
    state.consecutive_failures = trailing
    if state.stale_s is None:
        state.available = False
        state.unavailable_since = readings[0].ts if readings else None
    else:
        state.available = state.stale_s <= POLICY.stale_display_s
        if not state.available and oks:
            state.unavailable_since = oks[-1].ts

    # Computed once per evaluation and shared. detect_discontinuities is
    # O(window) and was previously being run three times per provider per
    # tick - twice inside estimate_burn and again for event detection -
    # which is most of why a cold replay scaled as O(n^1.85).
    state.readings = list(readings)
    state.cuts = detect_discontinuities(readings, state.pay_model)
    state.burn = estimate_burn(readings, state.pay_model, cuts=state.cuts)
    state.recent_burn = estimate_burn(readings, state.pay_model,
                                      window_s=BASELINE.recent_window_s,
                                      cuts=state.cuts)

    _project(state, now)
    return state


def build_state(store: Store, now: datetime, catalog: dict[str, dict[str, Any]],
                window_s: float = BASELINE.baseline_window_s) -> list[ProviderState]:
    since = now - timedelta(seconds=window_s)
    states: list[ProviderState] = []
    for provider, meta in catalog.items():
        # Bounded at `now`: state as of an instant must not see past it.
        readings = store.readings_since(provider, since, until=now)
        states.append(state_from_readings(provider, meta, readings, now))
    return states


def _project(state: ProviderState, now: datetime) -> None:
    """Fill in runway / projected-at-refresh, or leave them None and say why."""
    if state.pay_model in ACCUMULATING and state.value is not None and state.last_ok:
        hours = trailing_window_h(state.last_ok.extra)
        state.trailing_window_h = hours
        state.trailing_rate_per_h = state.value / hours
        # No balance exists, so there is no runway to compute. Deliberately
        # left None rather than filled with something plausible.
        return

    burn = state.burn
    if state.value is None or burn is None or not burn.ok or burn.rate_per_h is None:
        return
    rate = burn.rate_per_h

    if state.pay_model == "prepaid_balance":
        if rate > 0:
            state.runway_h = state.value / rate
            state.depleted_at = now + timedelta(hours=state.runway_h)
    elif state.pay_model == "postpaid":
        # Zero is not the boundary for postpaid credit: it may legitimately go
        # negative between top-ups. The configured floor stands in for the
        # credit limit nobody supplied.
        if rate > 0:
            headroom = state.value - POLICY.postpaid_floor
            if headroom > 0:
                state.runway_h = headroom / rate
                state.depleted_at = now + timedelta(hours=state.runway_h)
    elif state.pay_model == "credits_package":
        if rate > 0:
            state.runway_h = state.value / rate
            state.depleted_at = now + timedelta(hours=state.runway_h)
        if state.refresh:
            try:
                refresh_day = date.fromisoformat(str(state.refresh))
            except ValueError:
                return
            refresh_at = datetime.combine(refresh_day, datetime.min.time(), tzinfo=timezone.utc)
            hours = (refresh_at - now).total_seconds() / 3600.0
            state.hours_to_refresh = hours
            if hours > 0:
                state.projection_at_refresh = state.value - rate * hours
                if burn.span_s > 0:
                    # How far past the observed window this projection reaches.
                    # Carried into the alert so nobody mistakes a 32-minute
                    # observation extrapolated over 8 days for a measurement.
                    state.extrapolation_ratio = (hours * 3600.0) / burn.span_s
    # spend_report has no balance, so no runway exists to compute.


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

CLASS_POLICY = "operational_policy"
CLASS_DERIVED = "data_derived"

SEVERITY = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Candidate:
    """A rule condition holding, before sustain and materiality are applied.

    A candidate is not an alert. It becomes one only after it has held for its
    sustain period and crossed a materiality band it has not already announced.
    """

    key: str
    rule: str
    level: str
    provider: str | None
    text: str
    evidence: dict[str, Any]
    rule_class: str
    sustain_s: float
    signature: str


# Bucket edges for judging whether an alert has materially changed. Roughly
# doubling, because what matters is the order of magnitude of the time left,
# not its second significant figure: 44 h and 43 h call for the same response,
# 182 h and 45 h do not.
RUNWAY_BUCKETS_H = (2.0, 6.0, 12.0, 24.0, 48.0, 72.0, 168.0)
DEVIATION_BUCKETS = (10.0, 20.0, 50.0, 100.0)
STALE_BUCKETS_MIN = (30.0, 60.0, 180.0, 720.0)


def _band(value: float | None, edges: Sequence[float], *,
          higher_is_worse: bool) -> tuple[int, str]:
    """Return `(severity, label)` for `value`, where a higher severity is worse.

    Direction matters. For a runway a *smaller* number is worse; for an anomaly
    deviation or an outage duration a *larger* one is. Encoding that here is
    what lets the alerter speak when a condition deteriorates and stay quiet
    when it recovers — a line saying an anomaly fell from 20 to 14 MAD is not
    something anyone acts on.
    """
    index, label = len(edges), f"ge{edges[-1]:g}"
    if value is None:
        index, label = len(edges), "na"
    else:
        for position, edge in enumerate(edges):
            if value < edge:
                index, label = position, f"lt{edge:g}"
                break
    severity = index if higher_is_worse else (len(edges) - index)
    return severity, label


def _signature(severity: int, descriptor: str) -> str:
    """Pack severity into the signature so the store needs no extra column."""
    return f"{severity:02d}|{descriptor}"


def signature_severity(signature: str | None) -> int:
    """Severity of a stored signature; -1 when there is none to compare against."""
    if not signature:
        return -1
    head = signature.split("|", 1)[0]
    try:
        return int(head)
    except ValueError:
        return -1


def slower_by_one_dispersion(burn: Estimate) -> float | None:
    """The burn rate one dispersion slower, as a conservative lower bound.

    A projection is a claim about the future built on an estimated rate, and the
    estimate carries a spread. If the claim flips when the rate is taken one MAD
    slower, the data does not support it and we should not be waking anyone with
    it. This is deliberately not a tuned constant: the bound comes from the
    provider's own slope dispersion, so a steady provider is held to a tight
    bound and a noisy one to a loose one.

    MEASURED: two lines fail this test where the rest pass comfortably --
    `findymail` at 17:00Z and `bounceban` at 18:44Z, both projecting to exhaust
    with roughly a 15-hour margin against a burn whose MAD is a tenth of the
    rate. The `bounceban` line was independently flagged by the audit's
    counterfactual, which found it disappears when a +3 credit top-up is removed
    from its window. Two different checks reaching the same line is the reason
    to believe both.
    """
    if burn.rate_per_h is None:
        return None
    return max(0.0, burn.rate_per_h - (burn.dispersion or 0.0))


def _fmt(value: float | None, unit: str, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if unit == "credits":
        return f"{value:,.0f} credits"
    if unit in ("usd", "gbp"):
        symbol = {"usd": "USD", "gbp": "GBP"}[unit]
        return f"{value:,.2f} {symbol}"
    return f"{value:,.{digits}f} {unit}"


def rule_runway(state: ProviderState, now: datetime) -> Candidate | None:
    """Balance will hit its floor sooner than the configured lead time."""
    if state.pay_model not in ("prepaid_balance", "postpaid"):
        return None
    runway = state.runway_h
    burn = state.burn
    depleted_at = state.depleted_at
    if runway is None or burn is None or burn.rate_per_h is None or depleted_at is None:
        return None
    if runway > POLICY.runway_warning_h:
        return None
    if burn.span_s < BASELINE.min_projection_span_s:
        return None
    # Same discipline as the package projection: if a rate one dispersion
    # slower puts the runway back outside the alerting threshold, the window
    # does not support the claim.
    conservative = slower_by_one_dispersion(burn)
    if state.value is None or not conservative:
        return None
    floor_value = state.value - (0.0 if state.pay_model == "prepaid_balance"
                                 else POLICY.postpaid_floor)
    if floor_value / conservative > POLICY.runway_warning_h:
        return None
    level = "critical" if runway <= POLICY.runway_critical_h else "warning"
    runway_severity, runway_label = _band(runway, RUNWAY_BUCKETS_H, higher_is_worse=False)
    floor = 0.0 if state.pay_model == "prepaid_balance" else POLICY.postpaid_floor
    floor_text = "zero" if floor == 0 else _fmt(floor, state.unit)
    return Candidate(
        key=f"runway:{state.provider}",
        rule="runway",
        level=level,
        provider=state.provider,
        text=(
            f"{state.provider} ({state.name}, {state.pay_model}) reaches {floor_text} in "
            f"{runway:.1f} h at the observed burn of "
            f"{_fmt(burn.rate_per_h, state.unit)}/h; "
            f"{_fmt(state.value, state.unit)} left, projected {iso(depleted_at)}"
        ),
        evidence={
            "value": state.value,
            "unit": state.unit,
            "pay_model": state.pay_model,
            "floor": floor,
            "burn_per_h": round(burn.rate_per_h, 6),
            "runway_h": round(runway, 3),
            "depleted_at": iso(depleted_at),
            "estimator": "theil_sen",
            "samples": burn.samples,
            "observed_span_s": round(burn.span_s, 1),
            "threshold_h": POLICY.runway_critical_h if level == "critical" else POLICY.runway_warning_h,
        },
        rule_class=CLASS_POLICY,
        sustain_s=POLICY.estimate_sustain_s,
        signature=_signature(runway_severity, f"runway:{level}:{runway_label}"),
    )


def rule_package_exhaustion(state: ProviderState, now: datetime) -> Candidate | None:
    """A credits package is projected to run out before its refresh date."""
    if state.pay_model != "credits_package":
        return None
    projection = state.projection_at_refresh
    burn = state.burn
    package = state.package
    runway = state.runway_h
    hours_left = state.hours_to_refresh
    if projection is None or burn is None or burn.rate_per_h is None:
        return None
    if package is None or runway is None or hours_left is None:
        return None
    if burn.span_s < BASELINE.min_projection_span_s:
        return None
    shortfall = -projection
    if shortfall <= POLICY.package_shortfall_fraction * package:
        return None
    # The claim must survive the estimate's own uncertainty, not merely clear a
    # fraction of the package. A shortfall that vanishes when the rate is taken
    # one dispersion slower is not something the window supports.
    conservative = slower_by_one_dispersion(burn)
    if conservative is None or state.value is None:
        return None
    if state.value - conservative * hours_left >= 0:
        return None
    ratio = state.extrapolation_ratio
    pkg_severity, pkg_label = _band(runway, RUNWAY_BUCKETS_H, higher_is_worse=False)
    ratio_text = f" (projection extrapolates the observed window {ratio:.0f}x)" if ratio else ""
    return Candidate(
        key=f"package_exhaustion:{state.provider}",
        rule="package_exhaustion",
        level="critical" if runway <= POLICY.runway_critical_h else "warning",
        provider=state.provider,
        text=(
            f"{state.provider} ({state.name}) is projected to exhaust its credits package "
            f"{runway:.1f} h from now, {hours_left:.1f} h before the "
            f"{state.refresh} refresh; {state.value:,.0f} of {package:,.0f} credits left, "
            f"burning {burn.rate_per_h:,.0f} credits/h" + ratio_text
        ),
        evidence={
            "remaining": state.value,
            "package": package,
            "refresh": state.refresh,
            "unit": "credits",
            "burn_per_h": round(burn.rate_per_h, 3),
            "runway_h": round(runway, 3),
            "hours_to_refresh": round(hours_left, 2),
            "projected_at_refresh": round(projection, 1),
            "estimator": "theil_sen",
            "samples": burn.samples,
            "observed_span_s": round(burn.span_s, 1),
            "extrapolation_ratio": round(ratio, 1) if ratio else None,
        },
        rule_class=CLASS_POLICY,
        sustain_s=POLICY.estimate_sustain_s,
        signature=_signature(pkg_severity, f"package_exhaustion:{pkg_label}"),
    )


def rule_unavailable(state: ProviderState, now: datetime) -> Candidate | None:
    """No usable reading from one provider for longer than the tolerance.

    Deliberately per-provider. MEASURED over 66 exact cycles: 429 never hit
    more than one provider in the same cycle - not once - so the "429 is
    injected pool-wide" reading taken from the first minutes does not survive
    the window, and grouping availability pool-wide would hide real per-vendor
    outages. 5xx episodes are plainly per-provider, running 10-22 consecutive
    polls on one ID at a time.

    What stops 504 singles from becoming spam is the length of the staleness
    window itself, which is why this rule carries no additional sustain: the
    900 s it takes to become stale IS the sustain, and stacking another 300 s
    on top would push detection past the longest outage ever observed. The
    Alerter still requires the condition to survive one evaluation before
    firing, so a single glitched evaluation cannot produce a line.
    """
    if state.stale_s is None:
        if state.last_reading is None:
            return None
        stale_for = (now - state.last_reading.ts).total_seconds()
        detail = "no successful reading in the whole window"
    else:
        stale_for = state.stale_s
        detail = f"last value {stale_for / 60:.1f} min ago"
    if stale_for < POLICY.unavailable_alert_s:
        return None

    recent = state.last_reading
    stale_severity, stale_label = _band(stale_for / 60.0, STALE_BUCKETS_MIN,
                                        higher_is_worse=True)
    return Candidate(
        key=f"unavailable:{state.provider}",
        rule="unavailable",
        level="warning",
        provider=state.provider,
        text=(
            f"{state.provider} ({state.name}) has returned no usable value for "
            f"{stale_for / 60:.1f} min ({detail}); "
            f"{state.consecutive_failures} consecutive failed polls, "
            f"last state {recent.state if recent else 'none'}"
            + (f" HTTP {recent.http}" if recent and recent.http else "")
        ),
        evidence={
            "stale_s": round(stale_for, 1),
            "consecutive_failures": state.consecutive_failures,
            "last_state": recent.state if recent else None,
            "last_http": recent.http if recent else None,
            "last_ok_ts": iso(state.last_ok.ts) if state.last_ok else None,
            "tolerance_s": POLICY.unavailable_alert_s,
            "window_ok_fraction": round(state.health_pct / 100, 4) if state.health_pct is not None else None,
        },
        rule_class=CLASS_POLICY,
        sustain_s=0.0,
        signature=_signature(stale_severity, f"unavailable:{stale_label}"),
    )


def rule_burn_anomaly(state: ProviderState, now: datetime) -> Candidate | None:
    """Recent burn departs from the provider's own robust baseline.

    Data-derived: the threshold is k MADs of that provider's own pairwise slope
    distribution, not a number anybody chose. The scale is floored at a
    fraction of the baseline because MAD is exactly zero for the steadiest
    providers, which would otherwise make every deviation infinite.
    """
    base, recent = state.burn, state.recent_burn
    if base is None or recent is None or not base.ok or not recent.ok:
        return None
    if base.rate_per_h is None or recent.rate_per_h is None:
        return None
    if abs(base.rate_per_h) < 1e-9:
        return None
    scale = max(base.dispersion or 0.0,
                BASELINE.anomaly_scale_floor_fraction * abs(base.rate_per_h))
    delta = recent.rate_per_h - base.rate_per_h
    if scale <= 0 or abs(delta) < BASELINE.anomaly_k * scale:
        return None
    # Only an acceleration in spend is worth waking someone for. A slowdown is
    # recorded on the dashboard but is not an incident.
    if delta <= 0:
        return None
    dev_severity, dev_label = _band(abs(delta) / scale, DEVIATION_BUCKETS,
                                    higher_is_worse=True)
    factor = recent.rate_per_h / base.rate_per_h if base.rate_per_h else None
    # For a trailing spend report the compared quantity is the rate of change
    # of the reported total, which is an acceleration, not a spend rate. Saying
    # "burn accelerated to X/h" there would put a number in front of a human
    # that means something else entirely.
    if state.pay_model in ACCUMULATING:
        window = state.trailing_window_h or DEFAULT_TRAILING_H
        # State the rate, the baseline and the change as three separate numbers.
        # An earlier version read "climbing 12.50 USD/h faster than usual", which
        # attached "faster than usual" to the recent *rate* — the actual change
        # was +27.82/h, so the line understated the move by more than half. An
        # alert that misstates its own headline number is worse than silence.
        direction = "rising" if recent.rate_per_h >= 0 else "falling"
        headline = (
            f"{state.provider} ({state.name}) trailing-{window:.0f}h cost is now "
            f"{direction} at {_fmt(recent.rate_per_h, state.unit)}/h over the last "
            f"{recent.span_s / 60:.0f} min, against a window baseline of "
            f"{_fmt(base.rate_per_h, state.unit)}/h — a change of "
            f"{'+' if delta >= 0 else ''}{_fmt(delta, state.unit)}/h; reported cost now "
            f"{_fmt(state.value, state.unit)} per {window:.0f} h "
            f"({_fmt(state.trailing_rate_per_h, state.unit)}/h average)"
        )
    else:
        headline = (
            f"{state.provider} ({state.name}) burn accelerated to "
            f"{_fmt(recent.rate_per_h, state.unit)}/h over the last "
            f"{recent.span_s / 60:.0f} min against a window baseline of "
            f"{_fmt(base.rate_per_h, state.unit)}/h — a change of "
            f"{'+' if delta >= 0 else ''}{_fmt(delta, state.unit)}/h"
            + (f", {factor:.1f}x" if factor else "")
        )
    return Candidate(
        key=f"burn_anomaly:{state.provider}",
        rule="burn_anomaly",
        level="warning",
        provider=state.provider,
        text=headline + f"; deviation {abs(delta) / scale:.1f} MAD-equivalents",
        evidence={
            "recent_burn_per_h": round(recent.rate_per_h, 6),
            "baseline_burn_per_h": round(base.rate_per_h, 6),
            "unit": state.unit,
            "delta_per_h": round(delta, 6),
            "scale": round(scale, 6),
            "k": BASELINE.anomaly_k,
            "deviation_in_scale_units": round(abs(delta) / scale, 2),
            "recent_window_s": round(recent.span_s, 1),
            "baseline_window_s": round(base.span_s, 1),
            "estimator": "theil_sen",
        },
        rule_class=CLASS_DERIVED,
        sustain_s=POLICY.estimate_sustain_s,
        signature=_signature(dev_severity, f"burn_anomaly:{dev_label}"),
    )


def rule_collection_health(states: Sequence[ProviderState], now: datetime) -> Candidate | None:
    """Most of the pool is dark at once - the collector or the API, not a vendor.

    Counts providers past the *alert* staleness threshold, not the tighter
    display one. Using the display threshold here would page someone whenever
    half the pool went amber, and MEASURED, routine 5xx episodes overlap: three
    providers were simultaneously mid-episode at 16:22-16:24Z. Those heal
    themselves in minutes and nobody can act on them, so the pool rule has to
    mean "half the pool is genuinely dark" or it means nothing.
    """
    if not states:
        return None
    dark = [s for s in states
            if s.stale_s is None or s.stale_s >= POLICY.unavailable_alert_s]
    fraction = len(dark) / len(states)
    if fraction < POLICY.pool_error_fraction:
        return None
    unavailable = dark
    return Candidate(
        key="collection_health:pool",
        rule="collection_health",
        level="critical",
        provider=None,
        text=(
            f"{len(unavailable)} of {len(states)} providers ({fraction:.0%}) have returned no "
            f"value for over {POLICY.unavailable_alert_s / 60:.0f} min; worst observed in the "
            f"reference window was 4 of 15 failing in a single cycle and none stayed dark that "
            f"long, so this points at the collector or the API rather than at one vendor. "
            f"Affected: {', '.join(sorted(s.provider for s in unavailable))}"
        ),
        evidence={
            "evaluated_at": iso(now),
            "unavailable": sorted(s.provider for s in unavailable),
            "unavailable_count": len(unavailable),
            "total_providers": len(states),
            "fraction": round(fraction, 4),
            "threshold_fraction": POLICY.pool_error_fraction,
            "worst_observed_in_reference_window": "4/15 in a single cycle",
        },
        rule_class=CLASS_POLICY,
        sustain_s=POLICY.pool_error_sustain_s,
        signature=_signature(9, "collection_health"),
    )


PROVIDER_RULES: tuple[Callable[[ProviderState, datetime], Candidate | None], ...] = (
    rule_runway,
    rule_package_exhaustion,
    rule_unavailable,
    rule_burn_anomaly,
)


def evaluate(states: Sequence[ProviderState], now: datetime) -> list[Candidate]:
    candidates: list[Candidate] = []
    for state in states:
        for rule in PROVIDER_RULES:
            found = rule(state, now)
            if found is not None:
                candidates.append(found)
    pool = rule_collection_health(states, now)
    if pool is not None:
        candidates.append(pool)
    candidates.sort(key=lambda c: (SEVERITY.get(c.level, 9), c.key))
    return candidates


# --------------------------------------------------------------------------
# Alerting
# --------------------------------------------------------------------------


class Alerter:
    """Sustain, materiality bands, and durable append to alerts.jsonl.

    There is deliberately no cooldown here. A plain hourly cooldown was tried
    and the live log showed it restating unchanged conditions while burying the
    one line that had genuinely deteriorated; what replaced it is a band
    comparison, so a line is written when a condition starts and when it gets
    materially worse, never merely because time passed.


    Sustain is evaluated against the *data* clock, not the process clock, so a
    replay of the log reproduces exactly the alerts a live run would have
    produced. That is what makes "change a threshold, delete the DB, replay"
    a meaningful operation.
    """

    def __init__(self, store: Store, alerts_path: str) -> None:
        self.store = store
        self.alerts_path = alerts_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(alerts_path)), exist_ok=True)

    def process(self, candidates: Sequence[Candidate], now: datetime) -> list[dict[str, Any]]:
        active = {c.key: c for c in candidates}
        fired: list[dict[str, Any]] = []

        for key, candidate in active.items():
            prior = self.store.alert_state(key)
            since = parse_ts(prior["active_since"]) if prior and prior["active_since"] else None
            last_fired = prior["last_fired"] if prior else None
            # The signature of the line we last WROTE, not of the last thing we
            # evaluated. Updating it on every tick would let a condition drift
            # across a materiality band while suppressed and never announce it.
            fired_signature = prior["signature"] if prior else None

            if since is None:
                # Condition just became true: start the sustain clock, do not fire.
                self.store.set_alert_state(key, now, last_fired, fired_signature)
                continue

            held_for = (now - since).total_seconds()
            if held_for < candidate.sustain_s:
                self.store.set_alert_state(key, since, last_fired, fired_signature)
                continue

            if last_fired is not None:
                was = signature_severity(fired_signature)
                now_severity = signature_severity(candidate.signature)
                # A condition that cleared and came back. If that happened long
                # enough after the last line, it is a new incident; if it
                # happened minutes later it is the same condition flickering
                # across its own threshold, and the band comparison below
                # decides on the merits rather than on the flicker.
                recurred = since > parse_ts(last_fired)
                aged_out = (now - parse_ts(last_fired)).total_seconds() >= \
                    POLICY.incident_forget_s
                if not (recurred and aged_out):
                    if now_severity < was:
                        # Recovering. Not worth a line - nobody acts on an
                        # anomaly easing from 20 to 14 MAD - but the stored band
                        # is lowered so that sliding back down speaks again.
                        self.store.set_alert_state(key, since, last_fired,
                                                   candidate.signature)
                        continue
                    if now_severity == was:
                        # Same band as the line already written. Restating it
                        # would tell a human nothing they could act on
                        # differently, and the dashboard shows it as active.
                        self.store.set_alert_state(key, since, last_fired,
                                                   fired_signature)
                        continue
                    if (now - parse_ts(last_fired)).total_seconds() < POLICY.refire_min_gap_s:
                        # Worse, but too soon: bounds a value oscillating across
                        # a band edge.
                        self.store.set_alert_state(key, since, last_fired,
                                                   fired_signature)
                        continue

            payload = {
                "ts": iso(now),
                "level": candidate.level,
                "rule": candidate.rule,
                "rule_class": candidate.rule_class,
                "provider": candidate.provider,
                "text": candidate.text,
                "evidence": dict(candidate.evidence,
                                 sustained_s=round(held_for, 1),
                                 sustain_required_s=candidate.sustain_s,
                                 first_observed=iso(since),
                                 band=candidate.signature,
                                 previous_band=fired_signature),
            }
            ident = hashlib.sha256(f"{key}|{iso(now)}".encode()).hexdigest()[:16]
            if self.store.record_fired(ident, now, payload):
                self._append(payload)
                fired.append(payload)
            self.store.set_alert_state(key, since, iso(now), candidate.signature)

        # Conditions that stopped holding: clear the sustain clock, but keep
        # both last_fired and the band that was last announced.
        #
        # Wiping the band here was a spam vector. A condition sitting close to
        # its own threshold clears and returns every few minutes, and with no
        # memory of what had already been said, each return looked like a fresh
        # incident -- `bounceban` produced two lines an hour apart whose runway
        # had *improved*. Remembering the band means a return is judged on
        # whether anything got worse. `incident_forget_s` is what eventually
        # lets a genuine recurrence speak again.
        for row in self.store.conn().execute(
                "SELECT key, last_fired, signature FROM alert_state").fetchall():
            if row["key"] not in active:
                self.store.set_alert_state(row["key"], None, row["last_fired"],
                                           row["signature"])

        return fired

    def _append(self, payload: dict[str, Any]) -> None:
        # One JSON object on one physical line is a hard requirement of the
        # deliverable, so it is enforced rather than assumed.
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if "\n" in line or "\r" in line:
            raise ValueError("alert payload would break the one-object-per-line contract")
        with self._lock, open(self.alerts_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------


class Ingestor:
    """Replays raw_samples.jsonl, then tails it.

    The raw log is append-only and the sampler fsyncs each line, so a byte
    offset is a safe resume point. Reading and event detection are idempotent
    anyway, so a wrong offset costs time and never correctness.
    """

    OFFSET_KEY = "raw_offset"
    EVAL_KEY = "last_eval_ts"

    def __init__(self, store: Store, alerter: Alerter, raw_path: str,
                 since: datetime | None = None) -> None:
        self.store = store
        self.alerter = alerter
        self.raw_path = raw_path
        # Records before this instant are skipped entirely, so derived state
        # describes only the window from here on. This is what makes a "clean
        # window" possible without touching the capture: the raw log stays one
        # continuous file written by a collector that never restarted, and only
        # what we derive from it is scoped. It is the whole point of deriving
        # from an append-only log rather than holding state in memory.
        self.since = since
        self.stop = threading.Event()
        self.last_eval: datetime | None = None
        self.last_ingest_wall: datetime | None = None
        self.lines_read = 0
        self.replay_complete = threading.Event()
        self._known_catalog: dict[str, dict[str, Any]] = {}

    # -- offsets ---------------------------------------------------------
    def _load_offset(self) -> int:
        raw = self.store.get_state(self.OFFSET_KEY)
        if not raw:
            return 0
        try:
            offset = int(raw)
        except ValueError:
            return 0
        try:
            size = os.path.getsize(self.raw_path)
        except OSError:
            return 0
        # File shrank: it was rotated or replaced, so the offset is meaningless.
        return offset if offset <= size else 0

    # -- processing ------------------------------------------------------
    def _handle_catalog(self, record: dict[str, Any]) -> None:
        if record.get("http") != 200:
            return
        try:
            entries = json.loads(record.get("body") or "")
        except (ValueError, TypeError):
            return
        if not isinstance(entries, list) or not entries:
            return
        self.store.upsert_catalog(entries, parse_ts(record["ts"]))
        self._known_catalog = self.store.catalog()

    def process_batch(self, records: Sequence[dict[str, Any]]) -> int:
        readings: list[Reading] = []
        newest: datetime | None = None
        for record in records:
            kind = record.get("kind")
            if kind == "catalog":
                self._handle_catalog(record)
            elif kind == "balance":
                reading = read_sample(record)
                if reading is not None:
                    readings.append(reading)
            ts_raw = record.get("ts")
            if ts_raw:
                try:
                    ts = parse_ts(ts_raw)
                except ValueError:
                    continue
                if newest is None or ts > newest:
                    newest = ts
        self.store.add_readings(readings)
        if newest:
            self.last_ingest_wall = newest
        return len(readings)

    def maybe_evaluate(self, now: datetime, force: bool = False) -> list[dict[str, Any]]:
        """Run the rules at a data timestamp, at most once per cycle."""
        if not force and self.last_eval and (now - self.last_eval).total_seconds() < CYCLE_S:
            return []
        catalog = self._known_catalog or self.store.catalog()
        if not catalog:
            return []
        states = build_state(self.store, now, catalog)
        self._detect_events(states)
        candidates = evaluate(states, now)
        fired = self.alerter.process(candidates, now)
        self.last_eval = now
        self.store.put_state(self.EVAL_KEY, iso(now))
        return fired

    def _detect_events(self, states: Sequence[ProviderState]) -> None:
        """Record top-ups, resets and reverted blips. Never an alert - normal operations."""
        for state in states:
            if not state.depleting:
                continue
            for ts, kind, detail in state.cuts:
                self.store.add_event(ts, state.provider, kind,
                                     dict(detail, unit=state.unit, pay_model=state.pay_model))

    # -- drivers ---------------------------------------------------------
    def replay(self) -> int:
        """Read the log from the stored offset to EOF, evaluating as data advances."""
        offset = self._load_offset()
        total = 0
        if not os.path.exists(self.raw_path):
            self.replay_complete.set()
            return 0
        with open(self.raw_path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            batch: list[dict[str, Any]] = []
            batch_newest: datetime | None = None
            for line in handle:
                if not line.endswith("\n"):
                    # Partial trailing line: the sampler is mid-write. Stop here
                    # and leave the offset before it.
                    break
                offset += len(line.encode("utf-8"))
                record = _decode(line)
                if record is None:
                    continue
                if self.since is not None:
                    raw_ts = record.get("ts")
                    if not isinstance(raw_ts, str):
                        continue
                    try:
                        if parse_ts(raw_ts) < self.since:
                            continue
                    except ValueError:
                        continue
                total += 1
                batch.append(record)
                try:
                    ts = parse_ts(record["ts"])
                except (KeyError, ValueError):
                    ts = None
                if ts and (batch_newest is None or ts > batch_newest):
                    batch_newest = ts
                # Flush at cycle boundaries so rules see whole cycles.
                if record.get("kind") == "catalog" and len(batch) > 1:
                    self.process_batch(batch[:-1])
                    if batch_newest:
                        self.maybe_evaluate(batch_newest)
                    batch = [record]
                    batch_newest = ts
            if batch:
                self.process_batch(batch)
                if batch_newest:
                    self.maybe_evaluate(batch_newest)
            self.store.put_state(self.OFFSET_KEY, str(offset))
        self.lines_read += total
        self.replay_complete.set()
        return total

    def tail(self, poll_s: float = 2.0) -> None:
        while not self.stop.is_set():
            try:
                self.replay()
                # Even with no new data, re-evaluate on the wall clock so
                # staleness and unavailability still fire when the sampler dies.
                wall = now_utc()
                if self.last_eval is None or (wall - self.last_eval).total_seconds() >= CYCLE_S:
                    self.maybe_evaluate(wall, force=True)
            except Exception as exc:  # noqa: BLE001 - a bad line must not kill the loop
                print(f"[ingest] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self.stop.wait(poll_s)


class Collector:
    """Polls the API directly and appends verbatim records to the raw log.

    This exists so the deliverable is genuinely one file: `monitor.py --poll`
    collects, derives, alerts and serves with nothing else installed and no
    second process. Everything downstream is untouched — the collector writes
    exactly the record shape the ingestor already reads, so the replay path and
    the live path share every line of parsing, estimation and alerting rather
    than having two implementations that can drift apart.

    It is off by default and must stay off wherever the standalone sampler is
    running. The API should see one client, not two, and a second poller would
    both double the load and interleave a second writer into the same log.

    One deliberate difference from `raw_sampler.py`: this records `body_chars`,
    the pre-truncation length. The sampler stores `r.text[:8000]` with no way to
    tell afterwards whether anything was clipped; nothing in the observed window
    came within 1,578 characters of that bound, but "verbatim" should be
    checkable rather than argued, and new code can fix that without restarting
    the capture.
    """

    BODY_CAP = 8000
    USER_AGENT = "explee-spend-monitor/standalone"

    def __init__(self, raw_path: str, base_url: str, interval: float,
                 timeout: float, concurrency: int = 5) -> None:
        self.raw_path = raw_path
        self.base_url = base_url.rstrip("/")
        self.interval = interval
        self.timeout = timeout
        self.concurrency = max(1, concurrency)
        self.stop = threading.Event()
        self.cycles = 0
        self._providers: list[str] = []
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(raw_path)) or ".", exist_ok=True)

    # -- one request ------------------------------------------------------
    def probe(self, path: str, kind: str, provider: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        record: dict[str, Any] = {"ts": iso(now_utc()), "kind": kind,
                                  "provider": provider, "url": url}
        started = time.monotonic()
        request = urllib.request.Request(url, headers={"user-agent": self.USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
                content_type = response.headers.get("content-type")
        except urllib.error.HTTPError as exc:
            # 429/500/503 carry a JSON error envelope and 504 an HTML page.
            # Both are data about the provider, so the body is kept.
            raw = exc.read() if hasattr(exc, "read") else b""
            status = exc.code
            content_type = exc.headers.get("content-type") if exc.headers else None
        except Exception as exc:  # noqa: BLE001 - every transport failure is data
            record["http"] = None
            record["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            record["error"] = f"{type(exc).__name__}: {exc}"
            return record

        body = raw.decode("utf-8", errors="replace")
        record["http"] = status
        record["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
        record["body_chars"] = len(body)
        record["body"] = body[:self.BODY_CAP]
        record["content_type"] = content_type
        return record

    # -- one cycle --------------------------------------------------------
    def cycle(self) -> list[dict[str, Any]]:
        """Fetch the catalog, then every provider it lists, concurrently."""
        records = [self.probe("/providers", "catalog")]
        if records[0].get("http") == 200:
            try:
                parsed = json.loads(records[0]["body"])
                fresh = [p["provider"] for p in parsed
                         if isinstance(p, dict) and p.get("provider")]
                if fresh:
                    self._providers = fresh
            except (ValueError, TypeError, KeyError):
                # A catalog we cannot parse is not a reason to stop polling the
                # providers we already know about.
                pass

        if self._providers:
            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                futures = [pool.submit(self.probe, f"/{name}/balance", "balance", name)
                           for name in self._providers]
                records.extend(future.result() for future in futures)
        self.cycles += 1
        return records

    def append(self, records: Sequence[dict[str, Any]]) -> None:
        with self._lock, open(self.raw_path, "a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run(self) -> None:
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                self.append(self.cycle())
            except Exception as exc:  # noqa: BLE001 - a bad cycle must not end collection
                print(f"[collect] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self.stop.wait(max(1.0, self.interval - (time.monotonic() - started)))


def _decode(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


# --------------------------------------------------------------------------
# Snapshot for the dashboard and the API
# --------------------------------------------------------------------------


def risk_key(state: ProviderState) -> tuple[Any, ...]:
    """Sort order for the dashboard: most urgent first, never alphabetical.

    Tier 0 is anything with a firing alert, worst level first. Tier 1 is
    anything we cannot currently see, because an unknown balance is a risk in
    its own right. Tier 2 is everything with a finite time-to-impact, soonest
    first. Time-to-impact is hours, which is comparable across providers
    without ever putting USD, GBP and credits into the same arithmetic.
    """
    # A firing condition outranks a merely pending one: something has actually
    # been raised. Pending still outranks calm, because it is about to be.
    firing = [a for a in state.alerts if a.get("status") == "firing"]
    ranked = firing or state.alerts
    worst = min((SEVERITY.get(a["level"], 9) for a in ranked), default=9)
    if state.alerts:
        tier = 0 if firing else 1
        return (tier, worst, state.runway_h if state.runway_h is not None else 1e9,
                state.provider)
    if not state.available:
        return (2, 0, -(state.stale_s or 0), state.provider)
    if state.runway_h is not None:
        return (3, 0, state.runway_h, state.provider)
    return (4, 0, 0.0, state.provider)


def condition_status(store: Store, candidate: Candidate, now: datetime) -> dict[str, Any]:
    """Where a holding condition sits in its lifecycle.

    `pending`  the condition holds but no line has been written *for this
               episode*. Either the sustain period has not elapsed, or it has
               and the next evaluation will write one.
    `firing`   a line was written during this episode and it still holds.

    The distinction matters because `alerts.jsonl` is the record of what a human
    was actually told. A dashboard that renders both states the same way claims
    an incident was raised when it may not have been.

    "This episode" is the load-bearing part. A condition that fired, recovered
    and came back has a `last_fired` from the *previous* episode, and reading
    that as firing put the dashboard at odds with the alerter, which already
    computes `recurred = since > last_fired`. The UI was the one lying: it
    showed an incident as raised while `alerts.jsonl` contained no line for the
    new episode.
    """
    prior = store.alert_state(candidate.key)
    since = parse_ts(prior["active_since"]) if prior and prior["active_since"] else None
    last_fired = prior["last_fired"] if prior else None
    held = (now - since).total_seconds() if since else 0.0

    # A line belongs to the current episode only if it was written at or after
    # the episode began.
    fired_this_episode = bool(
        last_fired and since and parse_ts(last_fired) >= since)

    return {
        "status": "firing" if fired_this_episode else "pending",
        "held_s": round(held, 1),
        "sustain_s": candidate.sustain_s,
        "sustain_remaining_s": round(max(0.0, candidate.sustain_s - held), 1),
        "last_fired": last_fired,
        "last_fired_this_episode": fired_this_episode,
        "episode_since": iso(since) if since else None,
        "band": candidate.signature,
        "fired_band": prior["signature"] if prior else None,
        "deteriorated": bool(
            fired_this_episode and prior
            and signature_severity(candidate.signature) > signature_severity(prior["signature"])),
    }


def snapshot(store: Store, now: datetime | None = None) -> dict[str, Any]:
    now = now or now_utc()
    catalog = store.catalog()
    states = build_state(store, now, catalog)

    # A condition that is holding but has not yet written a line is *pending*,
    # not firing. Showing the two identically overstated the situation: the
    # table implied an incident had been raised when nothing had reached
    # alerts.jsonl and nobody had been told.
    active = {}
    conditions: list[dict[str, Any]] = []
    for candidate in evaluate(states, now):
        entry = dict(condition_status(store, candidate, now),
                     rule=candidate.rule,
                     level=candidate.level,
                     rule_class=candidate.rule_class,
                     provider=candidate.provider,
                     text=candidate.text,
                     evidence=candidate.evidence)
        active.setdefault(candidate.provider, []).append(entry)
        conditions.append(entry)
    conditions.sort(key=lambda c: (c["status"] != "firing", SEVERITY.get(c["level"], 9),
                                   c.get("provider") or ""))
    for state in states:
        state.alerts = active.get(state.provider, [])
        state.events = store.events(limit=6, provider=state.provider)

    states.sort(key=risk_key)
    coverage = store.coverage()
    fresh = [s for s in states if s.available]

    # Aggregate only where addition means something.
    #
    # Grouping on (pay_model, unit) is not sufficient, and the earlier version
    # of this code was wrong for exactly the reason the task warns about. Two
    # USD balances add up because a dollar at one vendor is a dollar at another.
    # Two "credits" balances do not: `elevenlabs` credits are TTS characters,
    # `resend` credits are emails, `scrapfly` credits are API calls. Summing
    # 850,199 of one and 40,076 of another produced a headline number that was
    # not a quantity of anything - and it sat in the one-glance summary.
    #
    # So a group is summed only when its unit is fungible across vendors, which
    # for this catalog means a currency. Vendor-specific quota units are
    # reported per provider and ranked by time-to-impact, which *is* comparable.
    groups: dict[str, dict[str, Any]] = {}
    for state in states:
        group_key = f"{state.pay_model}/{state.unit}"
        bucket = groups.setdefault(group_key, {
            "pay_model": state.pay_model,
            "unit": state.unit,
            "fungible": is_fungible_unit(state.unit),
            "providers": 0,
            "value": 0.0,
            "burn_per_h": 0.0,
            "measurable": 0,
            "unmeasurable": [],
            "members": [],
        })
        bucket["providers"] += 1
        rate = state.spend_rate_per_h
        if state.value is not None and rate is not None:
            bucket["measurable"] += 1
            bucket["members"].append({
                "provider": state.provider,
                "value": state.value,
                "burn_per_h": rate,
                "runway_h": state.runway_h,
            })
            if bucket["fungible"]:
                bucket["value"] += state.value
                bucket["burn_per_h"] += rate
        else:
            bucket["unmeasurable"].append(state.provider)

    # For a non-fungible group the only honest summary is the one that does not
    # add: how many packages, and which one runs out first.
    for bucket in groups.values():
        if bucket["fungible"]:
            continue
        bucket["value"] = None
        bucket["burn_per_h"] = None
        with_runway = [x for x in bucket["members"] if x["runway_h"] is not None]
        soonest = min(with_runway, key=lambda x: x["runway_h"], default=None)
        bucket["soonest"] = soonest

    window_span = 0.0
    if coverage["first_ts"] and coverage["last_ts"]:
        window_span = (parse_ts(coverage["last_ts"]) - parse_ts(coverage["first_ts"])).total_seconds()

    return {
        "generated_at": iso(now),
        "providers": states,
        "groups": groups,
        # Two different questions, deliberately not merged: `conditions` is what
        # is true now, `alerts` is what was written to the file a human reads.
        "conditions": conditions,
        "alerts": store.fired_alerts(limit=25),
        "events": store.events(limit=25),
        "coverage": dict(coverage, window_span_s=round(window_span, 1),
                         window_span_h=round(window_span / 3600.0, 3)),
        "healthy": bool(fresh),
        "fresh_providers": len(fresh),
        "total_providers": len(states),
        "policy": POLICY,
        "baseline": BASELINE,
    }


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#272e38;--fg:#e6edf3;--dim:#8b949e;
--crit:#f85149;--warn:#d29922;--ok:#3fb950;--info:#58a6ff;--accent:#a371f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:var(--info)}
header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;
flex-wrap:wrap;gap:16px;align-items:baseline;justify-content:space-between}
h1{font-size:16px;margin:0;letter-spacing:.02em}
h2{font-size:13px;margin:0 0 10px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em}
.wrap{padding:20px;max-width:1600px;margin:0 auto}
.meta{color:var(--dim);font-size:12px}
.grid{display:grid;gap:16px;margin-bottom:20px}
.cols{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px}
.card .big{font-size:20px;margin:4px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:600;font-size:11px;
text-transform:uppercase;letter-spacing:.06em;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:hover td{background:#1b222c}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;border:1px solid}
.p-crit{color:var(--crit);border-color:var(--crit)}
.p-warn{color:var(--warn);border-color:var(--warn)}
.p-ok{color:var(--ok);border-color:var(--ok)}
.p-dim{color:var(--dim);border-color:var(--line)}
.p-info{color:var(--info);border-color:var(--info)}
.p-acc{color:var(--accent);border-color:var(--accent)}
.dim{color:var(--dim)}
.crit{color:var(--crit)}.warn{color:var(--warn)}.ok{color:var(--ok)}
.alert{border-left:3px solid var(--line);padding:8px 12px;margin-bottom:8px;background:var(--panel);
border-radius:0 4px 4px 0}
.alert.critical{border-left-color:var(--crit)}
.alert.warning{border-left-color:var(--warn)}
.alert .t{font-size:12px}
.alert .e{color:var(--dim);font-size:11px;margin-top:3px;word-break:break-word}
.rowsub{color:var(--dim);font-size:11px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:1100px){.two{grid-template-columns:1fr}}
code{background:#21262d;padding:1px 5px;border-radius:3px;font-size:12px}
.foot{color:var(--dim);font-size:11px;margin-top:24px;line-height:1.7}
"""


def sparkline(values: Sequence[float], width: int = 150, height: int = 26) -> str:
    if len(values) < 2:
        return '<span class="dim">-</span>'
    low, high = min(values), max(values)
    span = high - low
    if span <= 0:
        mid = height / 2
        return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
                f'<line x1="0" y1="{mid:.1f}" x2="{width}" y2="{mid:.1f}" '
                f'stroke="#3fb950" stroke-width="1.5"/></svg>')
    step = width / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - 2 - (v - low) / span * (height - 4):.1f}"
        for i, v in enumerate(values)
    )
    colour = "#f85149" if values[-1] < values[0] else "#3fb950"
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none"><polyline points="{points}" fill="none" '
            f'stroke="{colour}" stroke-width="1.5" stroke-linejoin="round"/></svg>')


def _freshness_cell(state: ProviderState) -> str:
    if state.stale_s is None:
        return '<span class="pill p-crit">no data</span>'
    seconds = state.stale_s
    if seconds <= POLICY.stale_display_s / 2:
        cls, label = "p-ok", f"{seconds:.0f}s"
    elif seconds <= POLICY.stale_display_s:
        cls, label = "p-warn", f"{seconds:.0f}s"
    else:
        cls, label = "p-crit", f"{seconds / 60:.1f}m stale"
    return f'<span class="pill {cls}">{label}</span>'


def _impact_cell(state: ProviderState) -> str:
    if state.pay_model == "spend_report":
        return '<span class="dim">n/a (trailing spend)</span>'
    if state.runway_h is None:
        reason = state.burn.reason if state.burn and state.burn.reason else "not declining"
        return f'<span class="dim">{escape(str(reason))}</span>'
    hours = state.runway_h
    cls = "crit" if hours <= POLICY.runway_critical_h else ("warn" if hours <= POLICY.runway_warning_h else "")
    if hours < 48:
        text = f"{hours:.1f} h"
    else:
        text = f"{hours / 24:.1f} d"
    at = f'<div class="rowsub">{escape(iso(state.depleted_at))}</div>' if state.depleted_at else ""
    return f'<span class="{cls}">{text}</span>{at}'


def _burn_cell(state: ProviderState) -> str:
    burn = state.burn
    if state.pay_model in ACCUMULATING:
        rate = state.trailing_rate_per_h
        if rate is None:
            return '<span class="dim">no report yet</span>'
        window = state.trailing_window_h or DEFAULT_TRAILING_H
        trend = ""
        if burn and burn.ok and burn.slope_per_h is not None:
            sign = "+" if burn.slope_per_h >= 0 else ""
            trend = (f", trend {sign}{burn.slope_per_h:,.1f}/h"
                     if abs(burn.slope_per_h) >= 0.05 else ", steady")
        sub = f"{_fmt(state.value, state.unit)} per {window:.0f} h{trend}"
        return f'{escape(_fmt(rate, state.unit))}/h<div class="rowsub">{escape(sub)}</div>'

    if burn is None or not burn.ok or burn.rate_per_h is None:
        reason = burn.reason if burn and burn.reason else "no estimate"
        return f'<span class="dim">{escape(str(reason))}</span>'
    rate = burn.rate_per_h
    label = _fmt(rate, state.unit)
    sub = f"n={burn.samples}, {burn.span_s / 60:.0f} min"
    return f'{escape(label)}/h<div class="rowsub">{escape(sub)}</div>'


def _evidence_value(value: Any) -> str:
    """Compact, complete rendering of one evidence field."""
    if isinstance(value, float):
        return f"{value:,.6g}"
    if isinstance(value, list):
        return ",".join(str(v) for v in value) or "none"
    return str(value)


def render_dashboard(snap: dict[str, Any]) -> str:
    states: list[ProviderState] = snap["providers"]
    coverage = snap["coverage"]
    window_h = coverage["window_span_h"]
    firing = [a for s in states for a in s.alerts]
    criticals = sum(1 for a in firing if a["level"] == "critical")

    rows = []
    for state in states:
        pills = []
        for a in state.alerts:
            if a["status"] == "firing":
                cls = "crit" if a["level"] == "critical" else "warn"
                title = f'firing since {a["last_fired"]}'
                mark = ""
            else:
                cls = "dim"
                left = a["sustain_remaining_s"]
                title = (f'pending — {left:.0f}s of sustain left'
                         if left > 0 else 'pending — writes on the next evaluation')
                mark = "&hellip;"
            pills.append(f'<span class="pill p-{cls}" title="{escape(title)}">'
                         f'{escape(a["rule"])}{mark}</span> ')
        alert_pills = "".join(pills) or '<span class="dim">-</span>'
        events = "".join(
            f'<div class="rowsub">{escape(e["kind"])} {escape(e["ts"][11:19])}Z '
            f'{"+" if e["detail"].get("delta", 0) > 0 else ""}{e["detail"].get("delta", "")}</div>'
            for e in state.events[:2]
        ) or '<span class="dim">-</span>'
        value = _fmt(state.value, state.unit) if state.value is not None else "-"
        health = state.health_pct
        health_cls = "ok" if health and health >= 95 else ("warn" if health and health >= 80 else "crit")
        rows.append(f"""<tr>
<td><strong>{escape(state.provider)}</strong>
<div class="rowsub">{escape(state.name)}</div></td>
<td><span class="pill p-dim">{escape(state.pay_model)}</span>
<div class="rowsub">{escape(state.unit)}</div></td>
<td class="num">{escape(value)}</td>
<td class="num">{_burn_cell(state)}</td>
<td class="num">{_impact_cell(state)}</td>
<td>{sparkline(state.spark)}</td>
<td class="num">{_freshness_cell(state)}</td>
<td class="num"><span class="{health_cls}">{f"{health:.0f}%" if health is not None else "-"}</span>
<div class="rowsub">{state.ok_samples}/{state.total_samples}</div></td>
<td>{alert_pills}</td>
<td>{events}</td>
</tr>""")

    group_cards = []
    for key in sorted(snap["groups"]):
        group = snap["groups"][key]
        unit = group["unit"]
        missing = group["unmeasurable"]
        note = (f'<div class="rowsub">{len(missing)} not measurable: '
                f'{escape(", ".join(missing))}</div>') if missing else ""
        if not group["fungible"]:
            # No total: these balances are not denominated in the same thing.
            # The comparable quantity is time, so lead with which runs out first.
            soonest = group.get("soonest")
            if soonest and soonest["runway_h"] is not None:
                hours = soonest["runway_h"]
                lead = f"{hours:.1f} h" if hours < 48 else f"{hours / 24:.1f} d"
                sub = f'{escape(soonest["provider"])} exhausts first'
                cls = "crit" if hours <= POLICY.runway_critical_h else (
                    "warn" if hours <= POLICY.runway_warning_h else "")
            else:
                lead, sub, cls = "&mdash;", "no projection yet", "dim"
            group_cards.append(f"""<div class="card">
<h2>{escape(group["pay_model"])} &middot; {escape(unit)}</h2>
<div class="big {cls}">{lead}</div>
<div class="meta">{sub}</div>
<div class="big" style="font-size:15px">{group["measurable"]}/{group["providers"]} packages</div>
<div class="meta">not summed &mdash; one vendor's credit is not another's</div>{note}
</div>""")
            continue

        if group["pay_model"] == "spend_report":
            head = "trailing reported cost"
            rate_note = "window average, not a balance"
        else:
            head = "value on hand"
            rate_note = f"summed burn &mdash; {escape(unit.upper())} is fungible across vendors"
        group_cards.append(f"""<div class="card">
<h2>{escape(group["pay_model"])} &middot; {escape(unit)}</h2>
<div class="big">{escape(_fmt(group["value"], unit))}</div>
<div class="meta">{escape(head)} across {group["measurable"]}/{group["providers"]} providers</div>
<div class="big" style="font-size:15px">{escape(_fmt(group["burn_per_h"], unit))}/h</div>
<div class="meta">{rate_note}</div>{note}
</div>""")

    alert_blocks = []
    for alert in snap["alerts"][:12]:
        # Rendered in full as key=value pairs rather than a clipped JSON dump.
        # Truncating the dump cut it mid-token and put malformed JSON on screen,
        # which is a poor advertisement for a panel whose whole job is to carry
        # the evidence for a claim.
        evidence = escape(" · ".join(
            f"{key}={_evidence_value(val)}"
            for key, val in sorted(alert.get("evidence", {}).items())
            if val is not None
        ))
        alert_blocks.append(f"""<div class="alert {escape(alert.get("level", "info"))}">
<div class="t"><span class="pill p-{"crit" if alert.get("level") == "critical" else "warn"}">
{escape(alert.get("level", ""))}</span>
<span class="pill p-dim">{escape(alert.get("rule", ""))}</span>
<span class="pill p-{"acc" if alert.get("rule_class") == "data_derived" else "info"}">
{escape(alert.get("rule_class", ""))}</span>
<span class="dim">{escape(alert.get("ts", ""))}</span></div>
<div class="t" style="margin-top:4px">{escape(alert.get("text", ""))}</div>
<div class="e">{evidence}</div></div>""")
    if not alert_blocks:
        alert_blocks.append('<div class="alert"><div class="t dim">'
                            'No alert has fired since the window opened.</div></div>')

    # Conditions holding right now, which is a different question from what has
    # been written to alerts.jsonl. One is the present, the other is the record.
    condition_blocks = []
    for cond in snap["conditions"][:12]:
        if cond["status"] == "firing":
            badge = ('<span class="pill p-crit">firing</span>'
                     if cond["level"] == "critical"
                     else '<span class="pill p-warn">firing</span>')
            when = f'line written {escape(str(cond["last_fired"]))}'
            if cond["deteriorated"]:
                when += " &middot; <strong>worsened since</strong>, next evaluation writes again"
        else:
            badge = '<span class="pill p-dim">pending</span>'
            left = cond["sustain_remaining_s"]
            when = (f'held {cond["held_s"]:.0f}s of {cond["sustain_s"]:.0f}s required '
                    f'&mdash; {left:.0f}s before a line is written'
                    if left > 0 else
                    'sustain met &mdash; a line is written on the next evaluation')
        condition_blocks.append(f"""<div class="alert {escape(cond["level"])}">
<div class="t">{badge}
<span class="pill p-dim">{escape(cond["rule"])}</span>
<strong>{escape(str(cond.get("provider") or "pool"))}</strong></div>
<div class="t" style="margin-top:4px">{escape(cond["text"])}</div>
<div class="e">{when}</div></div>""")
    if not condition_blocks:
        condition_blocks.append('<div class="alert"><div class="t ok">'
                                'Nothing is currently in an alerting state.</div></div>')

    event_blocks = []
    for event in snap["events"][:12]:
        detail = event["detail"]
        delta = detail.get("delta")
        event_blocks.append(f"""<div class="alert">
<div class="t"><span class="pill p-acc">{escape(event["kind"])}</span>
<strong>{escape(event["provider"])}</strong>
<span class="dim">{escape(event["ts"])}</span></div>
<div class="e">{escape(str(detail.get("from")))} &rarr; {escape(str(detail.get("to")))}
({"+" if isinstance(delta, (int, float)) and delta > 0 else ""}{escape(str(delta))}
{escape(str(detail.get("unit", "")))}), gap {escape(str(detail.get("gap_s")))}s,
{escape(str(detail.get("ratio_to_typical")))}x typical decline &mdash;
recorded as an event, never alerted</div></div>""")
    if not event_blocks:
        event_blocks.append('<div class="alert"><div class="t dim">'
                            'No top-up or package reset observed in the window.</div></div>')

    stale = [s for s in states if not s.available]
    health_line = ('<span class="pill p-ok">collecting</span>' if snap["healthy"]
                   else '<span class="pill p-crit">no fresh data</span>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Explee spend monitor</title>
<meta http-equiv="refresh" content="30">
<style>{CSS}</style></head><body>
<header>
<div><h1>Explee &middot; company spend</h1>
<div class="meta">{snap["total_providers"]} providers &middot; four pay models &middot;
totals only where the unit is fungible</div></div>
<div class="meta">
{health_line}
<span class="pill {"p-crit" if criticals else ("p-warn" if firing else "p-ok")}">
{criticals} critical / {len(firing)} firing</span>
<span class="pill p-dim">window {window_h:.2f} h</span>
<span class="pill p-dim">{coverage["samples"]:,} samples</span>
<br><span class="dim">generated {escape(snap["generated_at"])} &middot;
T0 {escape(coverage["first_ts"] or "-")} &middot; last {escape(coverage["last_ts"] or "-")}
&middot; auto-refresh 30s</span></div>
</header>
<div class="wrap">

<div class="grid cols">{"".join(group_cards)}</div>

<h2>Providers, sorted by risk</h2>
<table><thead><tr>
<th>provider</th><th>pay model</th><th class="num">value</th><th class="num">burn</th>
<th class="num">time to impact</th><th>window</th><th class="num">freshness</th>
<th class="num">poll health</th><th>alerts</th><th>events</th>
</tr></thead><tbody>{"".join(rows)}</tbody></table>

<div class="two" style="margin-top:24px">
<div><h2>Conditions holding now ({len(snap["conditions"])})</h2>
<div class="meta" style="margin:-4px 0 10px">Live state. <em>pending</em> means the condition is
holding but nothing has been written yet &mdash; nobody has been told.</div>
{"".join(condition_blocks)}</div>
<div><h2>Lines written to alerts.jsonl ({len(snap["alerts"])})</h2>
<div class="meta" style="margin:-4px 0 10px">The record of what a human was actually told, newest
first. A line appears when a condition starts and when it crosses a materiality band.</div>
{"".join(alert_blocks)}</div>
</div>

<h2 style="margin-top:24px">Events &mdash; top-ups, resets and reverted blips</h2>
<div class="two">{"".join(event_blocks)}</div>

<h2 style="margin-top:24px">Collection health</h2>
<div class="grid cols">
<div class="card"><h2>window</h2><div class="big">{window_h:.2f} h</div>
<div class="meta">{escape(coverage["first_ts"] or "-")}<br>&rarr; {escape(coverage["last_ts"] or "-")}</div></div>
<div class="card"><h2>samples</h2><div class="big">{coverage["samples"]:,}</div>
<div class="meta">{coverage["ok_samples"]:,} carried a value
({100 * coverage["ok_samples"] / max(1, coverage["samples"]):.1f}%)</div></div>
<div class="card"><h2>sample states</h2>
<div class="meta">{"<br>".join(f"{escape(k)}: {v:,}" for k, v in sorted(coverage["by_state"].items()))}</div>
<div class="meta" style="margin-top:6px">schema_miss is <code>{{}}</code> on HTTP 200 &mdash;
a third state, never read as zero</div></div>
<div class="card"><h2>stale providers</h2>
<div class="big {"crit" if stale else "ok"}">{len(stale)}</div>
<div class="meta">{escape(", ".join(s.provider for s in stale)) or "all fresh"}</div>
<div class="meta" style="margin-top:6px">tolerance {POLICY.stale_display_s:.0f}s</div></div>
</div>

<div class="foot">
<strong>How to read this.</strong> Burn is a Theil&ndash;Sen slope over the readings since the
last top-up, not a first/last difference: in this window a first/last estimate reports
<code>findymail</code> burning &minus;3623 credits/h, because a +1994 top-up lands inside it.
Time to impact is hours, the only quantity comparable across every provider.<br>
<strong>What is and is not added up.</strong> A card shows a total only when its unit is
fungible across vendors, which here means a currency: a dollar of <code>openai</code> credit
and a dollar of <code>brightdata</code> credit are both a dollar. The six providers whose unit
is called &ldquo;credits&rdquo; are <em>not</em> summed &mdash; <code>elevenlabs</code> credits are
TTS characters, <code>resend</code> credits are emails, <code>scrapfly</code> credits are API
calls. They share a label, not a unit, so that card reports how many packages there are and
which one runs out first.<br>
<strong>Alert classes.</strong> <span class="pill p-info">operational_policy</span> rules encode
choices nobody specified (runway lead time {POLICY.runway_critical_h:.0f}h critical /
{POLICY.runway_warning_h:.0f}h warning, unavailability tolerance
{POLICY.unavailable_alert_s / 60:.0f}min, postpaid floor {POLICY.postpaid_floor:.0f}).
<span class="pill p-acc">data_derived</span> rules compute their threshold from the observed
window ({BASELINE.anomaly_k:.0f} MAD of the provider's own slope distribution).<br>
<strong>Why {POLICY.unavailable_alert_s / 60:.0f} minutes.</strong> In the reference window
transient 504/429 failures lasted 1&ndash;2 polls (30&ndash;60s) and self-healing 5xx episodes
lasted 10&ndash;22 polls (300&ndash;630s) &mdash; 15 of them across 10 providers in under three
hours, every one self-healing. The tolerance sits above the longest outage actually measured,
so a line means "longer than anything we observed", not "the API is flaky again".
Freshness above turns amber at {POLICY.stale_display_s:.0f}s so a provider going quiet is
<em>visible</em> long before it is <em>alerted</em>.<br>
<strong>Not alerts.</strong> A top-up, a package reset on its refresh date, a postpaid credit
going negative, a rise that is later handed back, and a single timeout are all normal.
Estimate-driven rules sustain for {POLICY.estimate_sustain_s:.0f}s before firing.<br>
<strong>Lines are written on change, not on a timer.</strong> A condition produces a line
when it starts and again only when it crosses a materiality band &mdash; roughly doubling
steps of time-to-impact. Drift inside a band is silent, because 44&nbsp;h and 43&nbsp;h call
for the same response. This table is the live state; <code>alerts.jsonl</code> is the log of
changes to it.<br>
<strong>Known measurement limit.</strong> A top-up landing in the same interval as spend is not
observable: the API exposes a current value only, so the two are seen summed and never
separately. Burn is a lower bound across such intervals.
</div>
</div></body></html>"""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def healthz(store: Store, replay_complete: bool,
            now: datetime | None = None) -> tuple[dict[str, Any], int]:
    """Health of the *data*, not of the process.

    A live process serving stale numbers is worse than an obvious outage: the
    dashboard looks normal and every figure on it is wrong. So this reports
    unhealthy when the process is up and every provider has gone stale, which
    is the case a plain liveness probe cannot see.

    The dashboard itself keeps serving 200 in that state on purpose - an
    operator investigating an unhealthy probe needs to be able to look at it.
    """
    now = now or now_utc()
    states = build_state(store, now, store.catalog(),
                         window_s=BASELINE.baseline_window_s)
    fresh = [s for s in states if s.available]
    coverage = store.coverage()
    healthy = bool(states) and bool(fresh)
    payload = {
        "status": "ok" if healthy else "unhealthy",
        "ts": iso(now),
        "providers_total": len(states),
        "providers_fresh": len(fresh),
        "providers_stale": sorted(s.provider for s in states if not s.available),
        "stale_tolerance_s": POLICY.stale_display_s,
        "samples": coverage["samples"],
        "last_sample_ts": coverage["last_ts"],
        "replay_complete": replay_complete,
        "reason": None if healthy else (
            "no providers in catalog" if not states
            else "every provider's data is stale"),
    }
    return payload, (200 if healthy else 503)


class Handler(BaseHTTPRequestHandler):
    server_version = "explee-spend-monitor"
    store: Store
    ingestor: Ingestor
    # Bound from the resolved CLI argument, not read from the module global.
    # Reading the global meant `--alerts /somewhere/else` wrote to one file and
    # served a different one, with no error on either side - the endpoint simply
    # published stale or absent content while looking like it worked.
    alerts_path: str

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            if path == "/":
                snap = snapshot(self.store)
                self._send(200, render_dashboard(snap).encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/healthz":
                body, code = self._healthz()
                self._send(code, body, "application/json")
            elif path == "/api/state":
                snap = snapshot(self.store)
                self._send(200, json.dumps(_jsonable(snap), default=str).encode("utf-8"),
                           "application/json")
            elif path == "/alerts.jsonl":
                data = b""
                if os.path.exists(self.alerts_path):
                    with open(self.alerts_path, "rb") as handle:
                        data = handle.read()
                self._send(200, data, "application/x-ndjson")
            else:
                self._send(404, b'{"error":"not found"}', "application/json")
        except Exception as exc:  # noqa: BLE001 - never take the server down
            # Log the traceback where an operator can find it, and tell the
            # client nothing beyond "it failed".
            #
            # This block used to do neither. It returned the exception text to
            # the caller - which on a public endpoint hands out internal paths
            # and types - while writing nothing to stderr, so a 500 seen from
            # outside left no trace on the server at all. A monitoring service
            # that cannot account for its own errors is not worth much.
            print(f"[error] {self.command} {self.path}: {type(exc).__name__}: {exc}",
                  file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            self._send(500, b'{"error":"internal error; see server log"}',
                       "application/json")

    def _healthz(self) -> tuple[bytes, int]:
        payload, code = healthz(self.store, self.ingestor.replay_complete.is_set())
        return json.dumps(payload, indent=2).encode("utf-8"), code

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base class name
        return  # access logs would add nothing here


def _jsonable(value: Any) -> Any:
    if isinstance(value, ProviderState):
        out = {
            k: _jsonable(v) for k, v in vars(value).items()
            if k not in ("spark_ts", "readings", "cuts")
        }
        out["health_pct"] = value.health_pct
        return out
    if isinstance(value, (Estimate, Policy, Baseline)):
        return {k: _jsonable(v) for k, v in vars(value).items()} if hasattr(value, "__dict__") \
            else {f: _jsonable(getattr(value, f)) for f in value.__dataclass_fields__}
    if isinstance(value, Reading):
        return {"provider": value.provider, "ts": iso(value.ts), "state": value.state,
                "value": value.value, "http": value.http, "shape": value.shape}
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def text_report(snap: dict[str, Any]) -> str:
    lines = []
    coverage = snap["coverage"]
    lines.append(f"generated {snap['generated_at']}")
    lines.append(f"window {coverage['window_span_h']:.3f} h  "
                 f"{coverage['first_ts']} -> {coverage['last_ts']}  "
                 f"{coverage['samples']} samples ({coverage['ok_samples']} with a value)")
    lines.append(f"states: {coverage['by_state']}")
    lines.append("")
    header = (f"{'provider':12s} {'pay_model':16s} {'unit':8s} {'value':>14s} "
              f"{'burn/h':>14s} {'impact_h':>10s} {'fresh_s':>8s} {'ok%':>6s}  alerts")
    lines.append(header)
    for state in snap["providers"]:
        rate = state.spend_rate_per_h
        burn = f"{rate:,.3f}" if rate is not None else "n/a"
        impact = f"{state.runway_h:,.1f}" if state.runway_h is not None else "-"
        value = f"{state.value:,.2f}" if state.value is not None else "-"
        fresh = f"{state.stale_s:.0f}" if state.stale_s is not None else "-"
        health = f"{state.health_pct:.0f}" if state.health_pct is not None else "-"
        rules = ",".join(a["rule"] for a in state.alerts) or "-"
        lines.append(f"{state.provider:12s} {state.pay_model:16s} {state.unit:8s} "
                     f"{value:>14s} {burn:>14s} {impact:>10s} {fresh:>8s} {health:>6s}  {rules}")
    lines.append("")
    for key in sorted(snap["groups"]):
        group = snap["groups"][key]
        measurable = f"({group['measurable']}/{group['providers']} measurable)"
        if not group["fungible"]:
            # No total exists for a vendor-specific quota; say so rather than
            # printing a number that is not a quantity of anything.
            soonest = group.get("soonest")
            first = (f"{soonest['provider']} in {soonest['runway_h']:.1f} h"
                     if soonest and soonest["runway_h"] is not None else "no projection")
            lines.append(f"{key:28s} not summed (unit is vendor-specific); "
                         f"soonest exhaustion: {first}  {measurable}")
            continue
        lines.append(f"{key:28s} value={group['value']:>16,.2f}  "
                     f"burn/h={group['burn_per_h']:>12,.3f}  {measurable}")
    lines.append("")
    lines.append(f"events: {len(snap['events'])}   alerts fired: {len(snap['alerts'])}")
    for alert in snap["alerts"][:10]:
        lines.append(f"  [{alert['level']:8s}] {alert['ts']} {alert['rule']}: {alert['text'][:150]}")
    return "\n".join(lines)


def _file_digest(path: str) -> str:
    """Short sha256 of a file, or a marker when it does not exist."""
    if not os.path.exists(path):
        return "absent"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def read_alert_lines(alerts_path: str) -> list[dict[str, Any]]:
    """Parse alerts.jsonl, one JSON object per physical line."""
    lines: list[dict[str, Any]] = []
    if os.path.exists(alerts_path):
        with open(alerts_path, encoding="utf-8") as handle:
            for raw in handle:
                if raw.strip():
                    lines.append(json.loads(raw))
    return lines


PROVIDER_RULE_BY_NAME: dict[str, Callable[[ProviderState, datetime], Candidate | None]] = {
    "runway": rule_runway,
    "package_exhaustion": rule_package_exhaustion,
    "unavailable": rule_unavailable,
    "burn_anomaly": rule_burn_anomaly,
}

# Evidence keys the alerter adds, rather than the rule. They are checked, but
# against the alerter's own invariants instead of against a re-run of the rule.
ALERTER_EVIDENCE_KEYS = frozenset({
    "sustained_s", "sustain_required_s", "first_observed", "band", "previous_band",
})

# Keys whose value legitimately drifts between the moment a line was written and
# a later re-derivation, because they describe the window rather than the claim.
DRIFTING_EVIDENCE_KEYS = frozenset({"observed_span_s", "samples", "evaluated_at"})


def _close_enough(claimed: Any, fresh: Any) -> bool:
    """Numbers within 2% (or 0.01 absolute) count as reproduced; others must match."""
    if isinstance(claimed, bool) or isinstance(fresh, bool):
        return claimed == fresh
    if isinstance(claimed, (int, float)) and isinstance(fresh, (int, float)):
        return abs(fresh - claimed) <= max(0.01, abs(claimed) * 0.02)
    return claimed == fresh


def _readings_without(readings: Sequence[Reading], cut_ts: datetime,
                      delta: float) -> list[Reading]:
    """The same series with one discontinuity undone.

    Subtracting the jump from every later reading answers a question a note
    beside an alert cannot: would this alert exist if the top-up, reset or
    reverted blip had never happened?
    """
    out: list[Reading] = []
    for reading in readings:
        if reading.state == STATE_OK and reading.value is not None and reading.ts >= cut_ts:
            out.append(Reading(reading.provider, reading.ts, reading.state,
                               reading.value - delta, reading.http, reading.latency_ms,
                               reading.shape, reading.extra))
        else:
            out.append(reading)
    return out


def audit_alerts(store: Store, lines: Sequence[dict[str, Any]]) -> tuple[str, int]:
    """Reconcile every field of every alert line against the raw window.

    An alert is a claim, and this re-derives the whole claim rather than spot
    checking it: the rule is re-run at the instant the line was written and
    every evidence field it produced is compared. Fields the alerter contributes
    -- sustain, bands -- are checked against the alerter's own invariants.

    Where a top-up, package reset or reverted blip sits close by, the incident is
    recomputed with that event undone. An alert that disappears when the event is
    removed was caused by normal operations and is reported as unreconciled; a
    note recording that an event happened nearby is not proof of anything.

    Returns the report and the number of lines that failed to reconcile.
    """
    catalog = store.catalog()
    out = [f"Reconciling {len(lines)} alert lines against the raw window", ""]
    failures = 0

    for index, alert in enumerate(lines, 1):
        provider = alert.get("provider")
        when = parse_ts(alert["ts"])
        claimed = alert.get("evidence", {})
        rule_name = alert["rule"]
        out.append(f"[{index}] {alert['ts']}  {alert['level']}  {rule_name}  {provider}")
        out.append(f"     {alert['text'][:160]}")
        problems: list[str] = []

        rule = PROVIDER_RULE_BY_NAME.get(rule_name)
        meta = catalog.get(provider) if provider else None
        state: ProviderState | None = None
        if provider and meta is not None and rule is not None:
            states = {s.provider: s for s in build_state(store, when, catalog)}
            state = states.get(provider)

        if state is None or rule is None or provider is None or meta is None:
            out.append("     (pool-wide or uncatalogued rule; field re-derivation skipped)")
        else:
            fresh = rule(state, when)
            if fresh is None:
                problems.append(f"rule {rule_name} does not fire when re-run at this instant")
            else:
                checked = 0
                for key, claimed_value in sorted(claimed.items()):
                    if key in ALERTER_EVIDENCE_KEYS or key in DRIFTING_EVIDENCE_KEYS:
                        continue
                    if key not in fresh.evidence:
                        problems.append(f"evidence field '{key}' is absent on re-run")
                        continue
                    checked += 1
                    if not _close_enough(claimed_value, fresh.evidence[key]):
                        problems.append(
                            f"field '{key}': line says {claimed_value!r}, "
                            f"re-run gives {fresh.evidence[key]!r}")
                out.append(f"     re-ran {rule_name}: {checked} evidence fields compared")

                # The band is the alerter's, but it must be the one this
                # candidate would produce.
                if claimed.get("band") and claimed["band"] != fresh.signature:
                    problems.append(f"band: line says {claimed['band']!r}, "
                                    f"candidate produces {fresh.signature!r}")

        # Alerter invariants.
        held, need = claimed.get("sustained_s"), claimed.get("sustain_required_s")
        if held is not None and need is not None:
            if held + 0.5 < need:
                problems.append(f"sustained {held}s below the required {need}s")
            else:
                out.append(f"     sustained {held:.0f}s of {need:.0f}s required")
        previous = claimed.get("previous_band")
        if previous and claimed.get("band"):
            if signature_severity(claimed["band"]) <= signature_severity(previous):
                problems.append(
                    f"re-fire did not worsen: {previous!r} -> {claimed['band']!r}")
            else:
                out.append(f"     band worsened {previous.split('|')[-1]} "
                           f"-> {claimed['band'].split('|')[-1]}")

        # Counterfactual: would this alert exist without the event?
        #
        # Every discontinuity in the estimation window is tested, not just ones
        # near the timestamp. A ±30 min filter was the first attempt and it
        # tested nothing at all: `bounceban`'s top-up sits 44 minutes before its
        # alert, yet it is inside the window whose slope produced that alert.
        # Proximity in time is the wrong question; being in the window the
        # estimate was fitted over is the right one.
        if state is not None and rule is not None and provider is not None and meta is not None:
            if not state.cuts:
                out.append("     no top-up, reset or blip in the estimation window, "
                           "so nothing to attribute the alert to")
            for cut_ts, kind, detail in state.cuts:
                delta = detail.get("delta")
                if not isinstance(delta, (int, float)):
                    continue
                counterfactual = state_from_readings(
                    provider, meta,
                    _readings_without(state.readings, cut_ts, float(delta)), when)
                still = rule(counterfactual, when)
                verdict = "survives" if still is not None else "DISAPPEARS"
                out.append(f"     without the {kind} at {iso(cut_ts)} "
                           f"({delta:+g}): the alert {verdict}")
                if still is None:
                    problems.append(
                        f"caused solely by a {kind} at {iso(cut_ts)}: "
                        f"removing it removes the alert")

        if problems:
            failures += 1
            for problem in problems:
                out.append(f"     UNRECONCILED: {problem}")
        else:
            out.append("     reconciled")
        out.append("")

    # Repeat lines for one key, explained rather than left to look like spam.
    grouped: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for alert in lines:
        grouped.setdefault((alert["rule"], alert.get("provider")), []).append(alert)
    repeats = {k: v for k, v in grouped.items() if len(v) > 1}
    if repeats:
        out.append("Repeat lines, and what each one added")
        out.append("")
        for (rule_name, provider), group in sorted(repeats.items(), key=lambda kv: str(kv[0])):
            out.append(f"  {provider} / {rule_name}: {len(group)} lines")
            for prior, line in zip(group, group[1:]):
                gap = (parse_ts(line["ts"]) - parse_ts(prior["ts"])).total_seconds()
                before = prior["evidence"].get("runway_h")
                after = line["evidence"].get("runway_h")
                moved = (f"runway {before:,.1f} h -> {after:,.1f} h"
                         if isinstance(before, (int, float)) and isinstance(after, (int, float))
                         else "band crossing")
                out.append(
                    f"    +{gap / 60:5.1f} min  "
                    f"{str(prior['evidence'].get('band', '')).split('|')[-1]} -> "
                    f"{str(line['evidence'].get('band', '')).split('|')[-1]}  {moved}")
        out.append("")

    out.append(f"unreconciled lines: {failures} of {len(lines)}")
    return "\n".join(out), failures



def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", default=RAW_PATH, help="raw_samples.jsonl to replay and tail")
    parser.add_argument("--db", default=DB_PATH, help="SQLite database for derived state")
    parser.add_argument("--alerts", default=ALERTS_PATH, help="alerts.jsonl to append to")
    parser.add_argument("--bind", default=BIND)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--once", action="store_true",
                        help="replay to EOF, print a report, exit (no server, no tail)")
    parser.add_argument("--audit", action="store_true",
                        help="replay, then reconcile every alerts.jsonl line against the raw "
                             "window that produced it; exits non-zero if any line does not "
                             "reconcile")
    parser.add_argument("--since", default=None,
                        help="ignore raw records before this ISO-8601 instant, so derived "
                             "state describes only the window from there on (the T1 clean "
                             "window). The raw log is not modified.")
    parser.add_argument("--as-of", default=None,
                        help="evaluate the report at this ISO-8601 instant instead of the "
                             "end of the log; only meaningful with --once")
    parser.add_argument("--no-serve", action="store_true", help="ingest only, no HTTP server")
    parser.add_argument("--poll", action="store_true",
                        help="collect from the API in this process as well as deriving from "
                             "the log, so this file is the whole system. Leave off wherever a "
                             "separate sampler is already writing the same log.")
    parser.add_argument("--api", default=API_BASE, help="API base URL for --poll")
    parser.add_argument("--poll-interval", type=float, default=POLL_INTERVAL_S,
                        help="seconds between --poll cycles")
    parser.add_argument("--poll-timeout", type=float, default=POLL_TIMEOUT_S,
                        help="per-request timeout for --poll")
    args = parser.parse_args(argv)

    audit_lines: list[dict[str, Any]] = []
    audit_scratch: str | None = None
    audit_digest_before: str | None = None
    db_path, alerts_path = args.db, args.alerts

    if args.audit:
        # An audit must not be able to change what it is auditing. Replaying
        # re-derives the window and appends, so the audit runs entirely on
        # throwaway paths and the submitted file is only ever read. The digest
        # is taken before and compared after, so "side-effect free" is checked
        # rather than intended.
        audit_lines = read_alert_lines(args.alerts)
        audit_digest_before = _file_digest(args.alerts)
        audit_scratch = tempfile.mkdtemp(prefix="explee-audit-")
        db_path = os.path.join(audit_scratch, "audit.sqlite")
        alerts_path = os.path.join(audit_scratch, "audit-alerts.jsonl")

    store = Store(db_path)
    alerter = Alerter(store, alerts_path)
    ingestor = Ingestor(store, alerter, args.raw,
                        since=parse_ts(args.since) if args.since else None)

    started = time.monotonic()
    count = ingestor.replay()
    # A replay that ends mid-cycle leaves the last cycle unevaluated; force one.
    if ingestor.last_ingest_wall:
        ingestor.maybe_evaluate(ingestor.last_ingest_wall, force=True)
    print(f"[replay] {count} records in {time.monotonic() - started:.1f}s from {args.raw}",
          file=sys.stderr, flush=True)

    if args.audit:
        report, unreconciled = audit_alerts(store, audit_lines)
        print(report)
        digest_after = _file_digest(args.alerts)
        untouched = digest_after == audit_digest_before
        print(f"\nauditee sha256[:16]: {audit_digest_before} -> {digest_after}  "
              f"{'unchanged' if untouched else 'MODIFIED'}")
        if audit_scratch:
            shutil.rmtree(audit_scratch, ignore_errors=True)
        if not untouched:
            print("the audit modified the file it was auditing", file=sys.stderr)
            return 1
        return 1 if unreconciled else 0

    if args.once:
        # Report as of the end of the log, not the wall clock. Replaying a
        # historical file at 03:00 the next morning would otherwise show all 15
        # providers as unavailable, which says something true about the file and
        # nothing at all about the providers.
        if args.as_of:
            as_of = parse_ts(args.as_of)
        else:
            as_of = ingestor.last_ingest_wall or now_utc()
        print(text_report(snapshot(store, as_of)))
        return 0

    collector: Collector | None = None
    if args.poll:
        # Collect first, then derive. The collector only appends to the raw log;
        # the ingestor picks the records up through exactly the same path it
        # uses for the bootstrap sampler's output, so there is one parsing and
        # alerting implementation rather than two that can drift.
        collector = Collector(args.raw, args.api, args.poll_interval, args.poll_timeout)
        first = collector.cycle()
        collector.append(first)
        providers = sum(1 for r in first if r.get("kind") == "balance")
        print(f"[collect] polling {args.api} every {args.poll_interval:.0f}s "
              f"-> {args.raw} ({providers} providers in the first cycle)",
              file=sys.stderr, flush=True)
        threading.Thread(target=collector.run, name="collect", daemon=True).start()

    thread = threading.Thread(target=ingestor.tail, name="ingest", daemon=True)
    thread.start()

    if args.no_serve:
        try:
            while thread.is_alive():
                thread.join(1.0)
        except KeyboardInterrupt:
            ingestor.stop.set()
            if collector is not None:
                collector.stop.set()
        return 0

    Handler.store = store
    Handler.ingestor = ingestor
    Handler.alerts_path = alerter.alerts_path
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"[serve] http://{args.bind}:{args.port}/  (healthz at /healthz)",
          file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ingestor.stop.set()
        if collector is not None:
            collector.stop.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
