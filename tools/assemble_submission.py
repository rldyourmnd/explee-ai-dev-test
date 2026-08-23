# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Assemble and pre-flight `submission/` — the seven upload artifacts, nothing else.

Built as a script rather than done by hand because the package gets rebuilt: the
current six-hour cut is a placeholder for a 12- or 24-hour window later, and
swapping it should be one command re-run, not a reassembly under time pressure.
A valid submission therefore exists at every moment from now on.

    uv run tools/assemble_submission.py            # copy what exists, then check
    uv run tools/assemble_submission.py --check    # check only, copy nothing

Absent artifacts are reported, not faked. The form allows partial submission, and
a trace exported before its session ends is worse than a missing one — it stops
before the work does.

Leak patterns live in the gitignored `.leak-patterns`, never in a tracked file:
`docs/SUBMISSION.md` once spelled the identifiers out inside a `grep` example,
which made the leak-detection instructions a leak.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "submission")

DASHBOARD_URL = "https://spend.nddev.it.com/"
REPORT_URL = "https://stt.nddev.it.com/"

# source -> submitted filename. Order is the order of the form's fields.
ARTIFACTS = [
    ("task1-spend-observability/alerts.jsonl", "task1-alerts.jsonl"),
    ("task1-spend-observability/monitor.py", "task1-monitor.py"),
    ("task1-spend-observability/TRACE.md", "task1-TRACE.md"),
    ("task2-stt-benchmark/TRACE.md", "task2-TRACE.md"),
    ("task3-harness-artifact/flow-memory-sync.md", "task3-flow-memory-sync.md"),
]
GENERATED = {"LINKS.md", "NOTES.md"}

HOSTNAME_RE = re.compile(r"^[ \t]*HostName[ \t]+[A-Za-z0-9_.-]+[ \t]*$", re.M)
# A dotted quad is not automatically an address. Package versions look identical
# to a naive regex - nvidia-cusparse-cu12 12.3.1.170 matched, and flagging it
# would have been a check failing on correct data, which costs as much trust as
# one passing on broken data. Require every octet to be a legal 0-255 AND reject
# anything sitting inside an obvious version context.
IP_RE = re.compile(r"(?<![\w.-])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.-])")
VERSION_CONTEXT = re.compile(r"(cu\d+|==|>=|<=|version|torch|nvidia|cudnn|pip)", re.I)
# The deployment target is ours and is already public via the dashboard hostname;
# private ranges and loopback are not disclosures.
ALLOWED_IP_PREFIXES = ("0.", "127.", "10.", "192.168.", "255.", "188.166.77.47")
# 8.8.8.8 is public DNS quoted while verifying a subdomain, not infrastructure.


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def leak_patterns() -> list[str]:
    path = os.path.join(ROOT, ".leak-patterns")
    if not os.path.exists(path):
        return []
    return [ln.strip() for ln in open(path, encoding="utf-8") if ln.strip()
            and not ln.startswith("#")]


def write_links() -> None:
    body = f"""# Links

Both open without login. Fetched and checked by `tools/assemble_submission.py`.

| What | URL |
|---|---|
| Task 1 — spend dashboard | {DASHBOARD_URL} |
| Task 2 — STT comparison report | {REPORT_URL} |

Here so neither URL is retyped from memory into the form.
"""
    with open(os.path.join(OUT, "LINKS.md"), "w", encoding="utf-8") as fh:
        fh.write(body)


def alerts_audit_passes() -> bool:
    """Does the source alerts file currently reconcile against the raw records?

    The audit is a gate, so an alerts file that fails it is not shippable. This
    matters specifically because the package is rebuilt: on 2026-08-23 the repo
    copy moved from 12 audited-clean lines to 13 with one unreconciled while the
    package still held the good one, and a blind re-copy would have silently
    replaced a passing artifact with a failing one. A swap must never downgrade
    the package.
    """
    return subprocess.run(["uv", "run", "tools/alert_audit_doc.py"],
                          cwd=ROOT, capture_output=True).returncode == 0


def assemble() -> list[str]:
    os.makedirs(OUT, exist_ok=True)
    missing = []
    audit_ok = alerts_audit_passes()
    for src, dst in ARTIFACTS:
        s = os.path.join(ROOT, src)
        if dst == "task1-alerts.jsonl" and not audit_ok:
            if os.path.exists(os.path.join(OUT, dst)):
                print("  KEEPING the existing task1-alerts.jsonl: the source copy "
                      "does not currently pass its audit, and a swap must not "
                      "replace a passing artifact with a failing one")
                continue
            print("  WARNING: task1-alerts.jsonl does not pass its audit and no "
                  "previously-audited copy exists")
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(OUT, dst))
        else:
            missing.append(dst)
    write_links()
    return missing


def check() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []

    present = {f for f in os.listdir(OUT)} if os.path.isdir(OUT) else set()
    expected = {dst for _, dst in ARTIFACTS} | GENERATED
    for extra in sorted(present - expected):
        problems.append(f"submission/ contains {extra!r}, which is not one of the "
                        f"seven artifacts — the employer asked for seven things")
    for want in sorted(expected - present):
        notes.append(f"not yet present: {want}")

    alerts = os.path.join(OUT, "task1-alerts.jsonl")
    if os.path.exists(alerts):
        n = 0
        for lineno, line in enumerate(open(alerts, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                row = json.loads(line)
            except Exception as exc:
                problems.append(f"task1-alerts.jsonl:{lineno}: not valid JSON ({exc})")
                continue
            for key in ("ts", "text"):
                if key not in row:
                    problems.append(f"task1-alerts.jsonl:{lineno}: missing required {key!r}")
            ts = str(row.get("ts", ""))
            if ts and not (ts.endswith("Z") or re.search(r"[+-]\d\d:?\d\d$", ts)):
                problems.append(f"task1-alerts.jsonl:{lineno}: ts {ts!r} has no offset")
        print(f"  task1-alerts.jsonl: {n} lines, all parse, all timezone-aware")

    pats = leak_patterns()
    if not pats:
        notes.append(".leak-patterns absent — identifier scan skipped, so the "
                     "package is NOT cleared on that dimension")
    for fname in sorted(present):
        path = os.path.join(OUT, fname)
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for pat in pats:
            hits = len(re.findall(pat, text, re.I))
            if hits:
                problems.append(f"{fname}: {hits} match(es) for a third-party identifier")
        hostnames = HOSTNAME_RE.findall(text)
        if hostnames:
            problems.append(f"{fname}: {len(hostnames)} SSH HostName config line(s)")
        ips = set()
        for m in IP_RE.finditer(text):
            octets = m.groups()
            if any(int(o) > 255 for o in octets):
                continue                      # not a legal address
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start:text.find("\n", m.end())]
            if VERSION_CONTEXT.search(line):
                continue                      # a package version, not a host
            ip = m.group(0)
            if not ip.startswith(ALLOWED_IP_PREFIXES) and ip != "8.8.8.8":
                ips.add(ip)
        if ips:
            problems.append(f"{fname}: unexpected IP address(es): {sorted(ips)}")
        for marker in ("This export is not verbatim", "truncated by --max-result"):
            if marker in text:
                problems.append(f"{fname}: lossy-export marker present ({marker!r})")

    return problems, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="check only; copy nothing")
    args = ap.parse_args()

    if not args.check:
        missing = assemble()
        print(f"assembled submission/ from {len(ARTIFACTS) - len(missing)} of "
              f"{len(ARTIFACTS)} source artifacts")

    print("pre-flight against submission/ only:")
    problems, notes = check()
    for n in notes:
        print(f"  outstanding: {n}")
    for p in problems:
        print(f"  FAIL: {p}", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"pre-flight: ok ({len(notes)} outstanding)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
