# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Insurance raw sampler: polls every provider, appends verbatim responses to JSONL.

No parsing, no interpretation. This log is a superset of anything a later
monitor needs, so it can be replayed into a real store once one exists.
"""
import asyncio, json, os, sys, time
from datetime import datetime, timezone
import httpx

BASE = "https://jobs.explee.com/ai-native-developer/test/api"
OUT = os.environ.get("RAW_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_samples.jsonl"))
INTERVAL = float(os.environ.get("RAW_INTERVAL", "30"))
TIMEOUT = float(os.environ.get("RAW_TIMEOUT", "10"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def emit(rec: dict) -> None:
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


async def probe(client: httpx.AsyncClient, sem: asyncio.Semaphore, path: str, kind: str, provider: str | None = None):
    async with sem:
        t0 = time.monotonic()
        rec = {"ts": now(), "kind": kind, "provider": provider, "url": f"{BASE}{path}"}
        try:
            r = await client.get(f"{BASE}{path}")
            rec["http"] = r.status_code
            rec["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
            rec["body"] = r.text[:8000]
            rec["content_type"] = r.headers.get("content-type")
        except Exception as exc:  # noqa: BLE001 - every transport failure is data
            rec["http"] = None
            rec["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
            rec["error"] = f"{type(exc).__name__}: {exc}"
        emit(rec)
        return rec


async def main() -> None:
    providers: list[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                 headers={"user-agent": "explee-spend-monitor/bootstrap"}) as client:
        while True:
            cycle_started = time.monotonic()
            sem = asyncio.Semaphore(5)
            cat = await probe(client, sem, "/providers", "catalog")
            if cat.get("http") == 200:
                try:
                    parsed = json.loads(cat["body"])
                    fresh = [p["provider"] for p in parsed if isinstance(p, dict) and "provider" in p]
                    if fresh:
                        providers = fresh
                except Exception as exc:  # noqa: BLE001
                    emit({"ts": now(), "kind": "catalog_parse_error", "error": str(exc)})
            if providers:
                await asyncio.gather(*[
                    probe(client, sem, f"/{p}/balance", "balance", p) for p in providers
                ])
            sleep_for = max(1.0, INTERVAL - (time.monotonic() - cycle_started))
            await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
