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
# Any full date on a line, used as the governing date for the BARE stamps that
# follow it in the same document. A bare time is only judgeable against a date
# the document actually states; see check body for why guessing "today" failed.
DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
# Bare time-of-day stamps like "21:46Z" are the dominant format in these
# documents and were completely unchecked by the dated pattern above, which
# requires a full ISO date. A 21:46Z stamp written at 21:42Z sailed through
# the gate that exists to catch exactly that.
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
                         r"will|window closes|not before|pending|"
                         # A PROJECTION is future by definition: the whole point
                         # of `depleted_at` is to name an instant that has not
                         # happened. This gate flagged a quoted alert line whose
                         # own text said "projected", which is a check failing on
                         # correct data - and one that would fire on any document
                         # quoting a runway alert. Added by NAME rather than by
                         # widening: "projects"/"projection"/"projected" all
                         # assert a forecast, never a past event.
                         r"project(s|ed|ion)?|reaches zero|runs out)\b", re.I)
    # A PAST assertion beats a forward word. The exemption above is line-level:
    # any forward word anywhere on a line exempted EVERY timestamp on it, so
    # "We projected the dashboard and verified it at <future>" sailed through.
    # That hole predates the projection vocabulary - "will", "until" and
    # "scheduled" all had it - so widening the list did not create it, but it
    # did widen it. Tested rather than reasoned about: both masked cases escaped.
    #
    # These verbs claim the timestamped thing ALREADY HAPPENED. When one appears
    # next to a future stamp the line is self-contradictory whatever else it
    # says, so the forward exemption does not apply.
    # Up to three words may sit between the verb and its preposition:
    # "verified IT at", "confirmed THE PAGE on". Bounded rather than open, so the
    # verb and the stamp stay associated instead of matching across a sentence.
    claimed_done = re.compile(r"\b(verified|confirmed|completed|finished|"
                              r"recorded|measured|observed|ran|happened|"
                              r"landed|shipped|passed|emitted)"
                              r"(\s+\w+){0,3}\s+(at|on)\b", re.I)
    for rel in CLAIM_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        governing_date: str | None = None
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            # Only a date in a HEADING governs the bare stamps beneath it. A date
            # inside a sentence is a fact being mentioned, not a declaration of
            # which day the section describes. Accepting prose dates re-dated a
            # whole document the moment one was added mid-file: adding the words
            # "the history rewrite of 2026-08-24" to a paragraph immediately made
            # every bare stamp below it fail as "in the future".
            if line.lstrip().startswith("#"):
                seen_date = DATE_RE.search(line)
                if seen_date:
                    governing_date = seen_date.group(0)
            for date, clock in TS_RE.findall(line):
                parts = [int(x) for x in clock.split(".")[0].split(":")]
                while len(parts) < 3:
                    parts.append(0)
                try:
                    stamp = dt.datetime(*[int(x) for x in date.split("-")], *parts,
                                        tzinfo=dt.timezone.utc)
                except ValueError:
                    continue
                if stamp > horizon and not (forward.search(line)
                                           and not claimed_done.search(line)):
                    _fail(problems, f"{rel}:{lineno}: timestamp {date}T{clock}Z is in the "
                                    f"future (now {now:%Y-%m-%dT%H:%M:%SZ})")
            if forward.search(line):
                continue
            # Scan for BARE times only on what is left after the fully-dated ones
            # are removed. `2026-08-23T18:45Z` is dated and was already judged
            # correctly above, but BARE_TS_RE still matched the `18:45Z` inside
            # it and re-judged it against TODAY - so every minute-precision
            # timestamp from a previous day turned into a "future" failure the
            # moment the clock passed midnight. 144 of them fired at once on the
            # first rollover, on data that was entirely correct. A stamp with
            # seconds escaped only because the lookbehind happened to block it,
            # which is luck, not a rule.
            for hh, mm in BARE_TS_RE.findall(TS_RE.sub(" ", line)):
                # The declared six-hourly snapshot cadence is future BY DESIGN.
                # Widening the forward-looking vocabulary until these stopped
                # matching would have blunted the check into uselessness; naming
                # the four scheduled instants keeps it sharp.
                if f"{hh}:{mm}" in SCHEDULED_INSTANTS:
                    continue
                # A bare time carries no date, so it can only be judged against
                # the date the document itself supplies. Without one the check is
                # UNDECIDABLE - `21:30Z` written yesterday about yesterday is
                # indistinguishable from `21:30Z` invented today - and the old
                # code resolved the ambiguity by assuming today. That held while
                # the run was one day long and broke at the first midnight: 141
                # correct lines failed at once. Guessing is not a weaker check,
                # it is a check that reports the calendar rather than the data.
                if governing_date != now.strftime("%Y-%m-%d"):
                    continue
                stamp = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                if stamp > horizon:
                    _fail(problems, f"{rel}:{lineno}: bare timestamp {hh}:{mm}Z is in the "
                                    f"future (now {now:%H:%M}Z, per the {governing_date} "
                                    f"heading above it)")


# Markdown a grader actually reads, and that WE authored. Deliberately an
# explicit list rather than "every tracked .md": `docs/TASK.md` is the verbatim
# task and carries 20 em dashes, and the exported traces carry dozens more.
# Sweeping those would be a gate satisfiable only by editing a verbatim record -
# the sixth unsatisfiable-check instance this run, and the second whose only
# passing state is a falsification. Authored prose is fixable; a record is not.
PROSE_DOCS = ["README.md", "AGENTS.md", "submission/NOTES.md", "submission/LINKS.md",
              "task1-spend-observability/README.md", "task2-stt-benchmark/README.md",
              "task3-harness-artifact/README.md"]
# U+2014 and U+2013. The two deployed pages were swept for these and the markdown
# never was, which is how five documents accumulated 82 of them unnoticed.
DASH_RE = re.compile(r"[\u2014\u2013]")


def check_no_dashes_in_prose(problems: list[str]) -> None:
    """No em or en dashes in the prose we wrote.

    House style, enforced on both deployed pages from early on. The markdown was
    never covered, so the rule held exactly where a machine checked it and
    drifted everywhere else - which is the argument for the check rather than
    against the rule.
    """
    for rel in PROSE_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        hits = []
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            for m in DASH_RE.finditer(line):
                name = "em dash" if m.group(0) == "\u2014" else "en dash"
                hits.append(f"{lineno} ({name})")
        if hits:
            shown = ", ".join(hits[:6]) + (" ..." if len(hits) > 6 else "")
            _fail(problems, f"{rel}: {len(hits)} em/en dash(es) at line {shown} - "
                            f"replace with a comma, colon, full stop or parentheses, "
                            f"and rewrite the sentence where the dash carried it")


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
        # A lossy marker counts only when the EXPORTER emitted it, not when the
        # exporter's own source is quoted inside a trace. task1's trace contains
        # the line `327:  f"result truncated by --max-result")` - the source of
        # the very check being described - and a bare substring test read that as
        # proof the trace was truncated. Same self-referential shape that made
        # the HostName gate unsatisfiable three times: a document discussing a
        # pattern is not an instance of it.
        #
        # This exact fix already existed in tools/assemble_submission.py and was
        # never propagated here, so one tool passed the trace and the other
        # failed it. Fixing a defect class in one of two copies is how a repo
        # ends up arguing with itself.
        # Match what the exporter RENDERS, not a phrase that also occurs in its
        # source. export_trace.py has two distinct paths: losses.append() at line
        # 490, which blocks the write outright and cannot coexist with
        # --submission, and the body marker at 493, which renders as
        # "[... N characters truncated by --max-result; ...]". Only the second is
        # evidence of a truncated trace.
        #
        # The previous line-start anchor happened to pass, but it discriminated
        # by WHERE the phrase sat rather than by what a marker is - so an
        # indented real marker would have slipped through, and that false
        # NEGATIVE is the dangerous direction for a gate guarding verbatimness.
        # The bracket-and-count form cannot match source and cannot miss an
        # indented marker.
        #
        # It also matters that the loose form was unsatisfiable by construction:
        # any verbatim trace of a session that READ export_trace.py contains the
        # phrase, so the only way to pass was to excise a legitimate tool result.
        # A check that can only be satisfied by deleting real evidence is worse
        # than no check.
        lossy = [
            (r"^[>\s]*This export is not verbatim", "header declares a lossy export"),
            (r"\[\.\.\. [0-9,]+ characters truncated by --max-result",
             "rendered body truncation marker"),
        ]
        for pattern, what in lossy:
            if re.search(pattern, body, re.M):
                _fail(problems, f"{rel}: lossy export - {what}")


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
    # Search every plausible location rather than one hard-coded directory. The
    # tool writes into task1-spend-observability/snapshots/, not repo-root
    # snapshots/, and a check pointed at the wrong path would have reported the
    # six-hour artifact missing while it sat on disk — the fifth instance of that
    # class in this run.
    metas = sorted(glob.glob(os.path.join(ROOT, "**", "snapshots", "*.json"),
                             recursive=True))
    if not metas:
        (problems.append if strict else NOTES.append)(
            "no snapshot in snapshots/ — the six-hour window is the one "
            "unrecoverable deliverable")
        return
    # "Latest" must mean the one that actually closes the requirement, not the
    # highest number. Snapshot 01 was taken 14 s after the six-hour instant by
    # wall clock but spans only 21587.8 s, because the span is measured between
    # the first and last RECORD and the last record precedes the snapshot by up
    # to one sample interval. Taking a snapshot at T0+6h does not guarantee a
    # six-hour span.
    qualifying = []
    for m in metas:
        try:
            d = json.load(open(m, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d.get("span_seconds"), (int, float)) and d["span_seconds"] >= 21600:
            qualifying.append(m)
    latest = qualifying[-1] if qualifying else metas[-1]
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


def _engine_tracks(payload: object) -> list[str]:
    """Every engine/track identifier discoverable in a results document.

    Written to search rather than to assume a shape: the results schema has
    already been reorganised once this run, and a check that hard-codes a key
    path is the same defect as one that hard-codes a directory.
    """
    for key in ("engines", "systems", "tracks", "by_engine", "results"):
        if isinstance(payload, dict) and key in payload:
            value = payload[key]
            if isinstance(value, dict) and value:
                return sorted(value)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                for ident in ("engine", "system", "name", "id"):
                    if ident in value[0]:
                        return sorted({r[ident] for r in value if ident in r})
    if isinstance(payload, dict):
        for value in payload.values():
            found = _engine_tracks(value)
            if found:
                return found
    return []


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

    # Prefer the COMMITTED evidence over directories on this machine. The raw
    # engine outputs are gitignored for size, so counting subdirectories asked
    # "did I run the engines here?" while claiming to answer "does this
    # submission prove five engines were compared?". Those differ for exactly
    # the reader who matters: on a clean clone of the published repository this
    # check FAILED under --strict while passing on the machine that ran the
    # benchmark. A gate that only passes where the work happened tests the
    # working environment, not the deliverable.
    for name in sorted(os.listdir(data)):
        if not (name.startswith("results-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(data, name), encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        tracks = _engine_tracks(payload)
        if not tracks:
            continue
        # "-default" / "-tuned" are configurations of one engine; the task asks
        # for five ENGINES, so a tuned track must not inflate the count.
        engines = sorted({re.sub(r"-(default|tuned)$", "", t) for t in tracks})
        if len(engines) < 5:
            (problems.append if strict else NOTES.append)(
                f"only {len(engines)} engines in {name}, task requires >=5: {engines}")
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
        check_no_dashes_in_prose(problems)
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
