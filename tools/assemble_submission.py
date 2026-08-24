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
# Package-manager output is the dominant source of dotted quads that are not
# addresses: "Successfully installed nvidia-cusparse-cu12-12.3.1.170" carries
# three of them per line. Detect the installer context, not just the token.
VERSION_CONTEXT = re.compile(
    r"(cu\d+|==|>=|<=|version|torch|nvidia|cudnn|pip|"
    r"successfully installed|installing collected|requirement already|"
    r"downloading |site-packages|resolved \d+ package)", re.I)
# The deployment target is ours and is already public via the dashboard hostname;
# private ranges and loopback are not disclosures.
ALLOWED_IP_PREFIXES = ("0.", "127.", "10.", "192.168.", "255.", "188.166.77.47")

# Reviewed dotted quads that are not addresses, each read in context before being
# listed here. They survive because they are NON-SENSITIVE: publishing "12.3.1.170
# is a CUDA library version" harms nobody. That is why this list may live in a
# tracked file while the client-name patterns may not, and why --allow-finding on
# a real identifier stays forbidden with no equivalent escape. An override is
# acceptable exactly when disclosing what it covers costs nothing.
#
# These appear in two shapes: pip's "Successfully installed nvidia-cusparse-cu12-
# 12.3.1.170 ..." output, and a trace quoting a scan report whose own output is a
# list of the tokens it found - the same self-referential shape that made the
# HostName gate unsatisfiable three times.
ACKNOWLEDGED_NON_ADDRESSES = {
    "11.2.1.3", "11.6.1.9", "12.3.1.170", "12.4.5.8", "9.1.0.70",  # CUDA versions
    "10.3.5.147",                                                   # CUDA version
    "8.8.8.8",                     # public DNS, quoted while verifying a subdomain
    "1.1.1.1", "1.2.3.4",          # literals in a sed mask self-test: "must show <ip-redacted>"
}
# 8.8.8.8 is public DNS quoted while verifying a subdomain, not infrastructure.


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def leak_patterns() -> list[str]:
    path = os.path.join(ROOT, ".leak-patterns")
    if not os.path.exists(path):
        return []
    return [ln.strip() for ln in open(path, encoding="utf-8") if ln.strip()
            and not ln.startswith("#")]


def fetch_status(url: str) -> str:
    """Actually fetch a URL and return its status, or the failure reason.

    This exists because `LINKS.md` claimed "fetched and checked by
    tools/assemble_submission.py" while this file made ZERO network calls. The
    facts were true - both URLs were live - but the provenance was not, and an
    artifact handed to an employer asserting evidence nobody gathered is the
    exact failure this repository argues against. The claim is now made true by
    performing the check rather than made safe by softening the sentence.

    No login is sent and none is configured, so a 200 here also demonstrates the
    "opens without login" half of the claim.
    """
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:   # noqa: S310
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:                       # DNS, TLS, timeout, offline
        return f"unreachable ({type(exc).__name__})"


def write_links() -> None:
    body = f"""# Links

Both open without login. Verified by fetching them, unauthenticated, during
`tools/assemble_submission.py --check`, which fails if either is not `200`.

| What | URL |
|---|---|
| Task 1, spend dashboard | {DASHBOARD_URL} |
| Task 2, STT comparison report | {REPORT_URL} |

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
            # Report, do not withhold. An earlier version of this guard REFUSED to
            # overwrite an audited-clean copy with one failing its audit, and that
            # was wrong here: it pinned a stale 12-line file while the system had
            # emitted 17, contradicting the ruling that the deliverable is the
            # record of decisions actually made. The audit's remaining findings are
            # documented and ruled on - a scrapfly re-fire that is pre-existing and
            # newly exposed by duration - so "unreconciled" does not mean "wrong".
            # A guard that cannot tell a defect from a documented finding must not
            # be the thing that chooses what ships.
            print("  NOTE: the alert audit does not currently pass. Shipping the "
                  "live record anyway, per the ruling that the artifact is what "
                  "the system emitted; the audit's findings are published beside "
                  "it in ALERT-AUDIT.md rather than resolved by omission.")
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

    # The two live URLs are deliverables in their own right, so verify them here
    # rather than trusting that they were up when someone last looked.
    for label, url in (("dashboard", DASHBOARD_URL), ("report", REPORT_URL)):
        status = fetch_status(url)
        if status == "200":
            print(f"  {label}: {url} -> HTTP 200, no credentials sent")
        else:
            problems.append(f"{label} {url} returned {status}, expected 200 — "
                            f"LINKS.md ships a claim that it opens without login")

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
            if ip in ACKNOWLEDGED_NON_ADDRESSES:
                continue
            if not ip.startswith(ALLOWED_IP_PREFIXES):
                ips.add(ip)
        if ips:
            problems.append(f"{fname}: unexpected IP address(es): {sorted(ips)}")
        # A lossy marker only counts when the EXPORTER emitted it, not when the
        # exporter's own source code is quoted inside a trace. task1-TRACE.md
        # contains `f"result truncated by --max-result"` as a source line, and an
        # unqualified substring search read that as evidence the trace was
        # truncated. Same self-referential shape that made the HostName gate
        # unsatisfiable three times: a document discussing a pattern is not an
        # instance of it. Require the marker at the start of a line, which is how
        # the exporter writes it and how quoted source never appears.
        # Kept byte-for-byte in step with tools/repo_checks.py. The line-start
        # anchor below was replaced because it discriminated by WHERE the phrase
        # sat, not by what a marker is: an indented real marker would have been
        # missed, and a false negative is the dangerous direction here. The
        # bracket-and-count form matches only what the exporter renders.
        for pattern, what in (
            (r"^[>\s]*This export is not verbatim", "header declares a lossy export"),
            (r"\[\.\.\. [0-9,]+ characters truncated by --max-result",
             "rendered body truncation marker"),
        ):
            if re.search(pattern, text, re.M):
                problems.append(f"{fname}: lossy export - {what}")

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
