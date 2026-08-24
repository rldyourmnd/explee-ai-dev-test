# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take an immutable, verifiable snapshot of the observation window.

The task asks for at least six hours of observation. A claim that six hours
happened is worth nothing on its own - a reviewer who cannot run anything has to
take it on trust - so this produces the artifact that settles it: the digest of
the exact bytes, the record and line counts, the precise first-to-last span, the
largest gap in collection, how many records were malformed, and the collector's
state immediately before and after.

Strictly read-only against the host. Nothing is restarted, nothing is written
there - the window cannot be recreated and this tool is never a reason to risk
it.

Verification is by *prefix*, which matters because the collector is still
writing while the snapshot is taken. Hashing the host file and then copying it
compares two different lengths and can never agree; the first rehearsal of this
tool failed exactly that way. Instead the file is copied first, the copy is
hashed, and the host is asked for the digest of the same leading byte count. If
those match, the snapshot is provably the bytes the collector wrote, and the log
being append-only is what makes a prefix the right thing to check.

Usage:
    uv run tools/snapshot_window.py --label six-hour
    uv run tools/snapshot_window.py --label six-hour --dry-run   # rehearse it
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
HOST = "server-nddev-amsterdam"
REMOTE_RAW = "/opt/explee-spend-monitor/data/raw_samples.jsonl"
REMOTE_ALERTS = "/opt/explee-spend-monitor/state/alerts.jsonl"
LOCAL_RAW = REPO / "task1-spend-observability" / "data" / "raw_samples.jsonl"
SNAPSHOT_DIR = REPO / "task1-spend-observability" / "snapshots"
SIX_HOURS_S = 21600
UNIT = "explee-raw-sampler"

# Any IPv4 literal is masked out of captured command output. The deployment
# target's address is published deliberately (see docs/RUNLOG.md), but that is a
# reviewed decision about the trace, not a licence for tooling to scatter it into
# generated files.
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def ssh(command: str) -> str:
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=30", HOST, command],
        capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"ssh failed ({result.returncode}): {result.stderr.strip()[:200]}")
    return IPV4.sub("<ip-redacted>", result.stdout.strip())


def collector_state() -> str:
    return ssh(f"systemctl is-active {UNIT} || true")


def parse_ts(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith(("z", "Z")):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def local_digest(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = lines = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
            size += len(chunk)
            lines += chunk.count(b"\n")
    return digest.hexdigest(), size, lines


def measure(path: Path, since: datetime | None = None) -> dict[str, Any]:
    """Everything the snapshot asserts, computed from the bytes on disk.

    `since` narrows the measurement to a sub-window without touching the file.
    That is how the clean post-T1 window is described: the raw log stays one
    continuous capture, and only what we derive from it is scoped.
    """
    per_provider: dict[str, list[datetime]] = {}
    all_ts: list[datetime] = []
    malformed = 0
    states: dict[str, int] = {}
    providers: set[str] = set()

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                malformed += 1
                continue
            if not isinstance(record, dict) or "ts" not in record:
                malformed += 1
                continue
            try:
                when = parse_ts(record["ts"])
            except ValueError:
                malformed += 1
                continue
            if since is not None and when < since:
                continue
            all_ts.append(when)
            if record.get("kind") == "balance" and record.get("provider"):
                providers.add(record["provider"])
                per_provider.setdefault(record["provider"], []).append(when)
                http = record.get("http")
                body = record.get("body")
                if http == 200 and isinstance(body, str):
                    key = "ok_or_schema_miss"
                elif http is None:
                    key = "transport_error"
                else:
                    key = f"http_{http}"
                states[key] = states.get(key, 0) + 1

    all_ts.sort()
    # The largest interval between consecutive cycles: the honest measure of
    # whether collection was continuous, since a gap is what would invalidate a
    # window that cannot be recreated.
    worst_gap = timedelta(0)
    worst_gap_at = None
    for earlier, later in zip(all_ts, all_ts[1:]):
        if later - earlier > worst_gap:
            worst_gap, worst_gap_at = later - earlier, earlier

    per_provider_gap = {}
    for provider, stamps in per_provider.items():
        stamps.sort()
        gap = max((b - a for a, b in zip(stamps, stamps[1:])), default=timedelta(0))
        per_provider_gap[provider] = gap.total_seconds()

    span = (all_ts[-1] - all_ts[0]) if len(all_ts) > 1 else timedelta(0)
    return {
        "records": len(all_ts) + malformed,
        "parsed_records": len(all_ts),
        "malformed_records": malformed,
        "first_ts": all_ts[0].isoformat().replace("+00:00", "Z") if all_ts else None,
        "last_ts": all_ts[-1].isoformat().replace("+00:00", "Z") if all_ts else None,
        "span_seconds": span.total_seconds(),
        "span_hours": span.total_seconds() / 3600.0,
        "max_gap_seconds": worst_gap.total_seconds(),
        "max_gap_at": worst_gap_at.isoformat().replace("+00:00", "Z") if worst_gap_at else None,
        "providers": len(providers),
        "provider_names": sorted(providers),
        "worst_provider_gap_seconds": max(per_provider_gap.values(), default=0.0),
        "response_classes": dict(sorted(states.items())),
    }


def next_sequence() -> int:
    """The next number in the snapshot sequence.

    Snapshots are taken every six hours and each is a standalone artifact, so
    they are numbered rather than named by time: a reader can see the sequence
    and its gaps at a glance, and the last one is unambiguous.
    """
    if not SNAPSHOT_DIR.exists():
        return 1
    used = [int(m.group(1)) for path in SNAPSHOT_DIR.glob("*.md")
            if (m := re.match(r"^(\d+)-", path.name))]
    return max(used, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="what this snapshot is, e.g. six-hour-minimum or clean-window")
    parser.add_argument("--since", default=None,
                        help="only measure records at or after this ISO-8601 instant, "
                             "for describing a sub-window such as the one after T1")
    parser.add_argument("--dry-run", action="store_true",
                        help="measure and print, write nothing")
    parser.add_argument("--sync-alerts", action="store_true",
                        help="ALSO overwrite the shipped task1 alerts.jsonl with "
                             "the host copy. Off by default: this tool used to do "
                             "it silently on every run, which mutated a shipped "
                             "deliverable and stranded every document quoting it.")
    parser.add_argument("--require-span-s", type=float, default=None,
                        help="fail unless the first-to-last RECORD span reaches this "
                             "many seconds. Use 21600 for the six-hour minimum. "
                             "Taking a snapshot at T0+6h does not produce a six-hour "
                             "span: the newest record precedes the snapshot by up to "
                             "one sample interval, so firing at the mark is short "
                             "essentially always.")
    args = parser.parse_args()

    print(f"collector before : {collector_state()}", file=sys.stderr)
    before = collector_state()
    if before != "active":
        raise SystemExit(f"collector is '{before}', refusing to snapshot a disturbed window")

    # Copy first, then verify. The log is append-only and the collector is still
    # writing, so hashing the host file and then copying it compares two
    # different lengths and never agrees - the first rehearsal of this tool
    # failed exactly that way. The correct invariant for an append-only file is
    # that the copy is a faithful *prefix*: hash the same leading byte count on
    # the host and require a match.
    subprocess.run(["rsync", "-az", f"{HOST}:{REMOTE_RAW}", str(LOCAL_RAW)], check=True)

    # alerts.jsonl is a SHIPPED DELIVERABLE, and this tool used to scp the host
    # copy straight over it on every run. That made a tool whose entire purpose
    # is producing an immutable record silently mutate an artifact - and every
    # document quoting that artifact went stale without anyone deciding
    # anything. It is how the file kept turning up dirty, and how the
    # POLICY-SENSITIVITY bullet, ALERT-AUDIT.md and three status documents came
    # within one commit of describing a file that no longer existed.
    #
    # Refreshing it is now something you ASK for. Default is to look and report:
    # a difference is information, and overwriting a deliverable is a decision.
    alerts_repo = REPO / "task1-spend-observability" / "alerts.jsonl"
    if args.sync_alerts:
        subprocess.run(["scp", "-q", f"{HOST}:{REMOTE_ALERTS}", str(alerts_repo)],
                       check=True)
        print(f"  alerts.jsonl REFRESHED from the host at your request -> "
              f"{sum(1 for _ in open(alerts_repo, encoding='utf-8'))} lines. "
              f"Everything quoting it must move in the same commit: "
              f"POLICY-SENSITIVITY.md, ALERT-AUDIT.md, and submission/ via "
              f"tools/assemble_submission.py.")
    else:
        host_lines = int(ssh(f"wc -l < {REMOTE_ALERTS}").split()[0])
        repo_lines = sum(1 for _ in open(alerts_repo, encoding="utf-8"))
        if host_lines != repo_lines:
            print(f"  alerts.jsonl NOT touched: repo has {repo_lines} lines, host "
                  f"has {host_lines}. The shipped artifact is a deliberate cut, "
                  f"not a mirror. Pass --sync-alerts to move it, and move every "
                  f"document that quotes it in the same commit.")

    sha, size, lines = local_digest(LOCAL_RAW)
    remote = ssh(f"head -c {size} {REMOTE_RAW} | sha256sum | cut -d' ' -f1; "
                 f"stat -c%s {REMOTE_RAW}")
    parts = remote.split()
    remote_sha = parts[0] if parts else ""
    remote_bytes_now = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    faithful = bool(remote_sha) and sha == remote_sha
    grew_by = max(0, remote_bytes_now - size)
    since = parse_ts(args.since) if args.since else None
    stats = measure(LOCAL_RAW, since)
    after = collector_state()
    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()

    seq = next_sequence()
    body = [
        f"# Window snapshot {seq:02d} - {args.label}",
        "",
        "Immutable record of the observation window.",
        "",
        "The collector was still writing when this was taken, so verification is",
        "by prefix: the file was copied down, the copy hashed, and the host asked",
        "for the digest of the same leading byte count. A match proves the",
        "measurements below describe the exact bytes the collector wrote. The log",
        "is append-only, which is what makes a prefix the right thing to check.",
        "",
        "Read-only. Nothing was restarted and nothing was written on the host -",
        "this window cannot be recreated, and no snapshot is worth risking it.",
        "",
        "| | |",
        "|---|---|",
        f"| snapshot | **{seq:02d}** in the six-hourly sequence |",
        f"| taken at | `{taken_at}` |",
        f"| label | `{args.label}` |",
        f"| repository | `{commit}` |",
        f"| collector before | `{before}` |",
        f"| collector after | `{after}` |",
        "",
        "## The bytes",
        "",
        "| | |",
        "|---|---|",
        f"| sha256 of the snapshot | `{sha}` |",
        f"| sha256 of the same leading bytes on the host | `{remote_sha}` |",
        f"| snapshot is a faithful prefix of the host file | **{'yes' if faithful else 'NO'}** |",
        f"| size | {size:,} bytes |",
        f"| lines | {lines:,} |",
        f"| host file had already grown by | {grew_by:,} bytes at verification time |",
        "",
        "## The window",
        "",
        ("" if not args.since else
         f"Scoped to records at or after `{args.since}`. The raw log itself is one "
         "continuous capture; only the measurement is narrowed.\n"),
        "| | |",
        "|---|---|",
        f"| first record | `{stats['first_ts']}` |",
        f"| last record | `{stats['last_ts']}` |",
        f"| span | **{stats['span_hours']:.4f} h** ({stats['span_seconds']:,.0f} s) |",
        f"| six hours reached | **{'yes' if stats['span_hours'] >= 6 else 'no'}** |",
        f"| records | {stats['records']:,} |",
        f"| malformed records | **{stats['malformed_records']}** |",
        f"| providers seen | {stats['providers']} |",
        "",
        "## Continuity",
        "",
        "A gap is the only thing that could invalidate a window that cannot be",
        "recreated, so it is measured rather than asserted.",
        "",
        "| | |",
        "|---|---|",
        f"| largest gap between cycles | **{stats['max_gap_seconds']:.1f} s** |",
        f"| at | `{stats['max_gap_at']}` |",
        f"| largest gap for any single provider | {stats['worst_provider_gap_seconds']:.1f} s |",
        "",
        "## Response classes observed",
        "",
        "| class | count |",
        "|---|---:|",
    ]
    for key, count in stats["response_classes"].items():
        body.append(f"| `{key}` | {count:,} |")
    body += [
        "",
        "## Providers",
        "",
        ", ".join(f"`{p}`" for p in stats["provider_names"]),
        "",
        "## Verifying this yourself",
        "",
        "```bash",
        "sha256sum task1-spend-observability/data/raw_samples.jsonl   # gitignored; rsync it first",
        "uv run tools/snapshot_window.py --label check --dry-run",
        "```",
        "",
    ]
    report = "\n".join(body)

    # State the condition the measurement actually met, next to the result.
    # Snapshot 01 of this run was taken 14 s after the six-hour instant and still
    # spanned only 21587.8 s, because wall-clock arrival and record span are
    # different quantities. Printing the span every time makes that visible
    # without anyone having to open the artifact.
    span = stats.get("span_seconds")
    required = args.require_span_s
    meets = None if required is None else (span is not None and span >= required)
    if span is not None:
        verdict = ""
        if required is not None:
            if meets:
                verdict = f"  required {required:.0f}s -> MEETS"
            else:
                verdict = (f"  required {required:.0f}s -> SHORT by "
                           f"{required - span:.3f}s")
        print(f"span             : {span:.3f}s = {span / 3600:.4f}h{verdict}",
              file=sys.stderr)

    if args.dry_run:
        print(report)
        print("DRY RUN - nothing written", file=sys.stderr)
        return 0 if faithful else 1

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{seq:02d}-{args.label}"
    out = SNAPSHOT_DIR / f"{stem}.md"
    out.write_text(report, encoding="utf-8")
    (SNAPSHOT_DIR / f"{stem}.json").write_text(
        json.dumps({"sequence": seq, "taken_at": taken_at, "label": args.label,
                    "since": args.since, "commit": commit,
                    "collector_before": before, "collector_after": after,
                    "sha256_snapshot": sha, "sha256_host_prefix": remote_sha,
                    "faithful_prefix": faithful, "bytes": size, "lines": lines,
                    "host_grew_by_bytes": grew_by,
                    "required_span_seconds": required,
                    "closes_six_hour_minimum": (span is not None
                                                and span >= SIX_HOURS_S),
                    **stats},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)}", file=sys.stderr)
    if not faithful:
        print("DIGEST MISMATCH - local copy is not the bytes on the host", file=sys.stderr)
        return 1
    if meets is False:
        print(f"SPAN TOO SHORT: {span:.3f}s < {required:.0f}s required. The window "
              f"is intact and nothing was disturbed; wait for further samples and "
              f"take another snapshot.", file=sys.stderr)
        return 1
    if after != "active":
        print(f"collector is '{after}' after the snapshot", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
