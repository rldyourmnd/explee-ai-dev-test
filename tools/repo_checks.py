# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Mechanical checks for the classes of defect this repository kept re-introducing.

Every check here exists because the defect it catches actually happened, was
found by a human or an external reviewer rather than by us, and would have been
caught by three lines of code. The external review at `fc2578` found six live
contradictions, including a verification stamped 19:45Z inside a commit made at
19:43:14Z, and an acceptance baseline pointing at an older SHA than HEAD.

Two subcommands:

    uv run tools/repo_checks.py consistency   # the repo does not contradict itself
    uv run tools/repo_checks.py acceptance    # the deliverables the task asks for

`consistency` runs in CI on every push and must stay green. `acceptance` reports
what is still missing and only fails under `--strict`, because it is a progress
measure until submission and a gate at it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Documents that make claims about the repository and are therefore checkable.
CLAIM_DOCS = ["README.md", "AGENTS.md", "docs/ACCEPTANCE.md", "docs/ORCHESTRATION.md",
              "docs/RUNLOG.md", "docs/HANDOFF.md"]

TS_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)T(\d\d:\d\d(?::\d\d(?:\.\d+)?)?)Z")
# Bare time-of-day stamps like "21:46Z" are the dominant format in these
# documents and were completely unchecked by the dated pattern above, which
# requires a full ISO date. A 21:46Z stamp written at 21:42Z sailed through
# the gate that exists to catch exactly that. Matched separately and dated to
# today, since that is what a bare stamp means in a same-day log.
BARE_TS_RE = re.compile(r"(?<![\d:-])([0-2]\d):([0-5]\d)Z\b")
# The snapshot series runs every six hours from the six-hour mark.
SCHEDULED_INSTANTS = {"22:14", "04:14", "10:14", "16:14"}
# Markdown links to repository-relative paths: not URLs, not anchors.
LINK_RE = re.compile(r"\[[^\]]*\]\((?!https?://|#|mailto:)([^)#\s]+)")


def _run(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _fail(problems: list[str], msg: str) -> None:
    problems.append(msg)


def check_baseline_not_behind_head(problems: list[str]) -> None:
    """The acceptance baseline must be real, and the matrix must not have been
    left behind while deliverables moved.

    An earlier version of this check demanded the baseline *equal* HEAD. That is
    unsatisfiable in a repository four sessions commit to: HEAD moves between
    staging the matrix and committing it, so the gate failed for reasons the
    author could not fix. Unsatisfiable gates are the exact defect this file
    exists to catch, and writing one here would have been the fourth instance.

    What actually matters is not that the baseline is the newest commit, but that
    nothing shipped since it without the matrix being reconsidered. So: the
    baseline must be an ancestor of HEAD, and if any deliverable path changed
    since the baseline, `docs/ACCEPTANCE.md` must have changed in that range too.
    """
    path = os.path.join(ROOT, "docs/ACCEPTANCE.md")
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    m = re.search(r"\*\*Baseline:?\s*`([0-9a-f]{7,40})`", text)
    if not m:
        _fail(problems, "docs/ACCEPTANCE.md: no `**Baseline: <sha>`** line found")
        return
    baseline = m.group(1)
    if subprocess.run(["git", "cat-file", "-e", baseline + "^{commit}"], cwd=ROOT,
                      capture_output=True).returncode != 0:
        _fail(problems, f"acceptance baseline {baseline} is not a commit in this repository")
        return
    if subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=ROOT,
                      capture_output=True).returncode != 0:
        _fail(problems, f"acceptance baseline {baseline} is not an ancestor of HEAD — "
                        f"it points at a commit this branch does not contain")
        return

    deliverables = ["task1-spend-observability", "task2-stt-benchmark",
                    "task3-harness-artifact", "tools", "tests"]
    moved = _run("git", "log", "--oneline", f"{baseline}..HEAD", "--", *deliverables)
    matrix = _run("git", "log", "--oneline", f"{baseline}..HEAD", "--", "docs/ACCEPTANCE.md")
    # An uncommitted edit to the matrix counts as revisiting it: otherwise the
    # gate blocks the very commit that fixes it, which is the unsatisfiable shape
    # again. In CI the tree is clean, so this branch never masks a real failure.
    dirty = _run("git", "status", "--porcelain", "--", "docs/ACCEPTANCE.md")
    if moved and not matrix and not dirty:
        n = len(moved.splitlines())
        _fail(problems, f"{n} commit(s) touched deliverables since baseline {baseline}, "
                        f"but docs/ACCEPTANCE.md was not revisited in that range — "
                        f"the matrix is the artifact a grader is handed as proof")


def check_no_future_timestamps(problems: list[str]) -> None:
    """No document may claim something happened later than now.

    A verification stamped after the commit that records it is not a typo: it
    means the time was estimated from cadence rather than read from a clock, and
    a pre-registration with a future freeze time destroys the property it exists
    to establish.
    """
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now + dt.timedelta(minutes=2)   # tolerate clock skew, not invention
    # A future timestamp is only a defect when the sentence claims something
    # already happened. Deadlines are supposed to be in the future: the six-hour
    # mark is the whole point of the run. Flagging those would train a reader to
    # ignore the check, which is worse than not having it.
    forward = re.compile(r"\b(mark|deadline|earliest|target|scheduled|due|"
                         r"at/after|at or after|remaining|until|before|by then|"
                         r"will|window closes|not before|pending)\b", re.I)
    for rel in CLAIM_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            for date, clock in TS_RE.findall(line):
                parts = [int(x) for x in clock.split(".")[0].split(":")]
                while len(parts) < 3:
                    parts.append(0)
                try:
                    stamp = dt.datetime(*[int(x) for x in date.split("-")], *parts,
                                        tzinfo=dt.timezone.utc)
                except ValueError:
                    continue
                if stamp > horizon and not forward.search(line):
                    _fail(problems, f"{rel}:{lineno}: timestamp {date}T{clock}Z is in the "
                                    f"future (now {now:%Y-%m-%dT%H:%M:%SZ})")
            if forward.search(line):
                continue
            for hh, mm in BARE_TS_RE.findall(line):
                # The declared six-hourly snapshot cadence is future BY DESIGN.
                # Widening the forward-looking vocabulary until these stopped
                # matching would have blunted the check into uselessness; naming
                # the four scheduled instants keeps it sharp.
                if f"{hh}:{mm}" in SCHEDULED_INSTANTS:
                    continue
                stamp = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                # Only same-day stamps are meaningful; a bare time far in the past
                # is yesterday's log, not a claim about the future.
                if stamp > horizon:
                    _fail(problems, f"{rel}:{lineno}: bare timestamp {hh}:{mm}Z is in the "
                                    f"future (now {now:%H:%M}Z)")


def check_referenced_paths_exist(problems: list[str]) -> None:
    """A document may not link to a file that is not there.

    Every quarantine and rename in this run left a dead link behind, and a README
    describing a file the reader cannot open is exactly what the first external
    review punished.
    """
    for rel in CLAIM_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        base = os.path.dirname(rel)
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            for target in LINK_RE.findall(line):
                candidates = [os.path.join(ROOT, target),
                              os.path.join(ROOT, base, target)]
                if not any(os.path.exists(c) for c in candidates):
                    _fail(problems, f"{rel}:{lineno}: links to missing path '{target}'")


def _trace_paths() -> list[str]:
    return ["task1-spend-observability/TRACE.md",
            "task2-stt-benchmark/TRACE.md",
            "task3-harness-artifact/TRACE.md"]


def check_traces(problems: list[str], strict: bool) -> None:
    """Three traces, tool-exported, with no lossy marker.

    `docs/TASK.md`: "Export that conversation as a TRACE.md per task ... every
    message and every correction, verbatim."
    """
    for rel in _trace_paths():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            (problems.append if strict else NOTES.append)(f"missing trace: {rel}")
            continue
        head = open(path, encoding="utf-8", errors="replace").read(4000)
        if "| Session id |" not in head:
            _fail(problems, f"{rel}: no exporter header — a hand-written trace is worthless")
        body = open(path, encoding="utf-8", errors="replace").read()
        for marker in ("This export is not verbatim", "truncated by --max-result"):
            if marker in body:
                _fail(problems, f"{rel}: contains a lossy-export marker ({marker!r})")


def check_alerts_schema(problems: list[str], strict: bool) -> None:
    """`docs/TASK.md`: required keys `ts` (with offset) and `text`; `provider` recommended."""
    rel = "task1-spend-observability/alerts.jsonl"
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        (problems.append if strict else NOTES.append)(f"missing {rel}")
        return
    n = 0
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            row = json.loads(line)
        except Exception as exc:
            _fail(problems, f"{rel}:{lineno}: not valid JSON ({exc})")
            continue
        for key in ("ts", "text"):
            if key not in row:
                _fail(problems, f"{rel}:{lineno}: missing required key '{key}'")
        ts = str(row.get("ts", ""))
        if ts and not (ts.endswith("Z") or re.search(r"[+-]\d\d:?\d\d$", ts)):
            _fail(problems, f"{rel}:{lineno}: ts '{ts}' carries no timezone offset")
    if n == 0:
        (problems.append if strict else NOTES.append)(f"{rel} is empty")


def check_snapshot(problems: list[str], strict: bool) -> None:
    """The six-hour window, proven by an immutable snapshot rather than asserted.

    Looks for the numbered series `snapshots/NN-*.json`, not a fixed filename.
    An earlier version hard-coded `docs/SNAPSHOT-22-14Z.md`, which the snapshot
    tool never writes — so the check would have reported the artifact missing
    forever while it sat on disk. That is the same defect as the engine count
    pointing at the pre-amendment directory: a check aimed at a path someone
    later renamed is worse than no check, because it is believed.
    """
    import glob
    metas = sorted(glob.glob(os.path.join(ROOT, "snapshots", "*.json")))
    if not metas:
        (problems.append if strict else NOTES.append)(
            "no snapshot in snapshots/ — the six-hour window is the one "
            "unrecoverable deliverable")
        return
    latest = metas[-1]
    rel = os.path.relpath(latest, ROOT)
    try:
        meta = json.load(open(latest, encoding="utf-8"))
    except Exception as exc:
        _fail(problems, f"{rel}: not valid JSON ({exc})")
        return
    flat = json.dumps(meta).lower()
    for token in ("sha256", "span", "gap"):
        if token not in flat:
            _fail(problems, f"{rel}: no '{token}' recorded")
    # The snapshot's own integrity property: the copy's digest must equal the
    # host's digest over the same leading byte count. A snapshot that failed its
    # prefix check is not evidence of anything, so it must not pass silently
    # just because the file exists and carries a span.
    if meta.get("faithful_prefix") is False:
        _fail(problems, f"{rel}: faithful_prefix is false — the copy does not match "
                        f"the host's prefix digest, so this snapshot proves nothing")
    for key in ("collector_before", "collector_after"):
        if meta.get(key) not in (None, "active"):
            _fail(problems, f"{rel}: {key} is {meta.get(key)!r}, not 'active'")

    span = None
    for key in ("span_s", "span_seconds", "window_span_s", "elapsed_s"):
        if isinstance(meta.get(key), (int, float)):
            span = meta[key]
            break
    if span is None:
        (problems.append if strict else NOTES.append)(
            f"{rel}: no numeric span field found; cannot assert >= 21600 s")
    elif span < 21600:
        (problems.append if strict else NOTES.append)(
            f"{rel}: span {int(span)}s is under the required 21600s")
    else:
        print(f"snapshot {rel}: span {int(span)}s >= 21600s")


def check_engines(problems: list[str], strict: bool) -> None:
    """`docs/TASK.md`: "a comparison of >=5 STT engines ... on the same audio".

    Counts the *active* corpus, not a hard-coded directory. The corpus was
    amended once mid-run to a talk that ships a publisher human transcript, which
    created `data/raw-<slug>/` alongside the original `data/raw/`. A check still
    pointed at the old path reported three engines while four had run — a check
    measuring the wrong thing is worse than no check, because it is believed.
    """
    data = os.path.join(ROOT, "task2-stt-benchmark/data")
    if not os.path.isdir(data):
        (problems.append if strict else NOTES.append)("no Task 2 data directory")
        return
    candidates = []
    for name in os.listdir(data):
        if name == "raw" or name.startswith("raw-"):
            path = os.path.join(data, name)
            if os.path.isdir(path):
                engines = sorted(d for d in os.listdir(path)
                                 if os.path.isdir(os.path.join(path, d)))
                candidates.append((len(engines), name, engines))
    if not candidates:
        (problems.append if strict else NOTES.append)("no engine output directories")
        return
    # The active corpus is the one with the most engines: an amended corpus is
    # only meaningful once engines have actually run against it.
    count, where, engines = max(candidates)
    if count < 5:
        (problems.append if strict else NOTES.append)(
            f"only {count} engines have raw output in {where}, task requires >=5: {engines}")


def check_report_not_placeholder(problems: list[str], strict: bool) -> None:
    """The report is Task 2's main artifact, so a stub at the URL is not delivery."""
    rel = "task2-stt-benchmark/report/index.html"
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        (problems.append if strict else NOTES.append)(f"missing {rel}")
        return
    text = open(path, encoding="utf-8", errors="replace").read()
    if "Report in preparation" in text or len(text) < 2000:
        (problems.append if strict else NOTES.append)(
            f"{rel}: still a placeholder ({len(text)} bytes)")


NOTES: list[str] = []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["consistency", "acceptance"])
    ap.add_argument("--strict", action="store_true",
                    help="acceptance: treat missing deliverables as failures (use at submission)")
    args = ap.parse_args()

    problems: list[str] = []
    if args.mode == "consistency":
        check_baseline_not_behind_head(problems)
        check_no_future_timestamps(problems)
        check_referenced_paths_exist(problems)
    else:
        check_traces(problems, args.strict)
        check_alerts_schema(problems, args.strict)
        check_snapshot(problems, args.strict)
        check_engines(problems, args.strict)
        check_report_not_placeholder(problems, args.strict)

    for note in NOTES:
        print(f"outstanding: {note}")
    for problem in problems:
        print(f"FAIL: {problem}", file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"{args.mode}: ok" + (f" ({len(NOTES)} still outstanding)" if NOTES else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
