# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export a Claude Code session to a verbatim TRACE.md.

The employer asked for the REAL conversation, so this renders every user and
assistant turn in order, including reasoning blocks, tool calls with their full
inputs, and tool results. Nothing is paraphrased and nothing is dropped.

Secrets are handled by refusing, not by redacting: silently rewriting the
transcript would break the verbatim guarantee that makes the trace worth
reading. If a credential pattern is found the export aborts and names the turn,
so the leak gets fixed at the source instead of being papered over.

Usage:
    uv run tools/export_trace.py --session <uuid> --out task1/TRACE.md --title "Task 1"
    uv run tools/export_trace.py --list            # this project only
    uv run tools/export_trace.py --list --project <slug>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

def project_slug(path: Path | str) -> str:
    """Claude Code's on-disk directory name for a working directory.

    Session logs live at `~/.claude/projects/<slug>/<uuid>.jsonl`, where the
    slug is the absolute working directory with every separator replaced by a
    dash. A slug is therefore a filesystem path, which is why discovery in this
    tool is scoped rather than global: see `list_sessions`.
    """
    return str(Path(path).resolve()).replace("/", "-")


# Patterns that must never reach a published trace. Ordered most specific first
# so the reported reason is the useful one.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer token", re.compile(r"[Bb]earer\s+[A-Za-z0-9._\-]{24,}")),
    # Deliberately context-bound: a bare 40-hex string is far more often a git
    # SHA than a credential, and false positives here would train the operator
    # to reach for --allow-secrets, which defeats the whole guard.
    ("assigned api key", re.compile(
        # No \b prefix: the interesting names are suffixes of longer identifiers
        # such as DEEPGRAM_API_KEY, where \b would never fire.
        r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret[_-]?key|password)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}")),
]

ROLE_LABEL = {"user": "User", "assistant": "Assistant"}


def load(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def fence(text: str, lang: str = "") -> str:
    """Wrap in a fence long enough to survive fences inside the payload."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    bar = "`" * max(3, longest + 1)
    return f"{bar}{lang}\n{text}\n{bar}"


def render_tool_result(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    parts.append("[image omitted from markdown; present in raw JSONL]")
                else:
                    parts.append(json.dumps(block, ensure_ascii=False, indent=2))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False, indent=2)


# A line carrying this pragma is vouched for by the author as a non-secret —
# a test fixture, a documentation example. Scoping the exemption to one line is
# the point: a blanket --allow-secrets for a whole export would hide a real leak
# sitting three turns away from the fixture that needed the exemption.
ALLOWLIST_PRAGMA = re.compile(r"pragma:\s*allowlist secret", re.IGNORECASE)


def fingerprint(name: str, matched: str) -> str:
    """Stable id for one finding.

    Deliberately derived from the matched text rather than the turn number:
    a session grows while it is being worked on, so turn indices shift under
    you and every acknowledgement goes stale within minutes. The digest is
    truncated because it only needs to distinguish findings, and a full hash of
    a credential is still a thing worth not writing down at length.
    """
    return f"{name}:{hashlib.sha256(matched.encode('utf-8')).hexdigest()[:12]}"


def scan_secrets(text: str) -> list[str]:
    """Report fingerprints of credential patterns, ignoring allowlisted lines."""
    found: list[str] = []
    for line in text.splitlines() or [text]:
        if ALLOWLIST_PRAGMA.search(line):
            continue
        for name, pat in SECRET_PATTERNS:
            match = pat.search(line)
            if match:
                ident = fingerprint(name, match.group(0))
                if ident not in found:
                    found.append(ident)
    return found


def ts_of(record: dict) -> str | None:
    return record.get("timestamp")


def human_ts(raw: str | None) -> str:
    if not raw:
        return "?"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%SZ")
    except ValueError:
        return raw


def build(records: list[dict], title: str, session_id: str, source: Path,
          max_result: int | None) -> tuple[str, list[str]]:
    turns = [r for r in records if r.get("type") in ("user", "assistant")
             and isinstance(r.get("message"), dict)]
    if not turns:
        raise SystemExit("no conversation turns found in session")

    models = {r["message"].get("model") for r in turns
              if r.get("type") == "assistant" and r["message"].get("model")}
    efforts = {r.get("effort") for r in turns if r.get("effort")}
    n_user = sum(1 for r in turns if r["type"] == "user")
    n_asst = len(turns) - n_user
    n_side = sum(1 for r in turns if r.get("isSidechain"))
    started, finished = human_ts(ts_of(turns[0])), human_ts(ts_of(turns[-1]))
    cwd = next((r.get("cwd") for r in turns if r.get("cwd")), "?")
    version = next((r.get("version") for r in turns if r.get("version")), "?")

    out: list[str] = [
        f"# {title}",
        "",
        "| | |",
        "|---|---|",
        "| Agent | Claude Code |",
        f"| Version | `{version}` |",
        f"| Model | {', '.join(sorted(models)) or 'unknown'} |",
        f"| Reasoning effort | {', '.join(sorted(e for e in efforts if e)) or 'default'} |",
        f"| Session id | `{session_id}` |",
        f"| Working directory | `{cwd}` |",
        f"| Started (UTC) | {started} |",
        f"| Finished (UTC) | {finished} |",
        f"| Turns | {n_user} user, {n_asst} assistant |",
        f"| Subagent turns | {n_side} |",
        f"| Export method | verbatim render of `{source.name}` by `tools/export_trace.py` |",
        "",
        "> This is the real session transcript, rendered turn by turn from the "
        "Claude Code session log. Reasoning blocks, tool calls, tool output, "
        "failed attempts and corrections are all included, in order. Nothing "
        "was rewritten after the fact.",
        "",
        "---",
        "",
    ]

    findings: list[str] = []
    for index, record in enumerate(turns, start=1):
        message = record["message"]
        role = record["type"]
        label = ROLE_LABEL.get(role, role)
        if record.get("isSidechain"):
            label += " (subagent)"
        out.append(f"## [{index}] {label} · {human_ts(ts_of(record))}")
        out.append("")

        content = message.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            content = []

        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")

            if kind == "text":
                body = block.get("text", "")
                findings += [f"{n}  (first seen: turn {index}, text)" for n in scan_secrets(body)]
                out += [body, ""]

            elif kind == "thinking":
                body = block.get("thinking", "")
                findings += [f"{n}  (first seen: turn {index}, thinking)" for n in scan_secrets(body)]
                out += ["<details><summary>Reasoning</summary>", "", fence(body), "",
                        "</details>", ""]

            elif kind == "tool_use":
                payload = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
                findings += [f"{n}  (first seen: turn {index}, tool input)" for n in scan_secrets(payload)]
                out += [f"**Tool call — `{block.get('name')}`**", "",
                        fence(payload, "json"), ""]

            elif kind == "tool_result":
                body = render_tool_result(block.get("content"))
                findings += [f"{n}  (first seen: turn {index}, tool result)" for n in scan_secrets(body)]
                if max_result is not None and len(body) > max_result:
                    dropped = len(body) - max_result
                    body = (body[:max_result]
                            + f"\n\n[... {dropped} characters truncated by "
                              f"--max-result; full output is in the raw session JSONL ...]")
                status = " (error)" if block.get("is_error") else ""
                out += [f"**Tool result{status}**", "", fence(body), ""]

        out.append("---")
        out.append("")

    return "\n".join(out), findings


def list_sessions(project: str | None) -> int:
    """List sessions for exactly one project.

    Scoped deliberately. This listing goes into a trace that publishes verbatim,
    and an earlier unscoped version globbed every project on the machine, so a
    single --list put 20 rows of unrelated client project names into a Task 3
    trace and forced it to be quarantined. Nothing here may widen past the one
    project the caller asked for - including the error path, which must not
    name the projects it found instead.
    """
    slug = project or project_slug(Path.cwd())
    target = PROJECTS / slug
    if not target.is_dir():
        print(f"no sessions for project {slug!r} under {PROJECTS}.\n"
              f"pass --project <slug> if the trace lives elsewhere.", file=sys.stderr)
        return 2

    rows = []
    for jsonl in target.glob("*.jsonl"):
        stat = jsonl.stat()
        rows.append((stat.st_mtime, jsonl.stem, stat.st_size))
    for mtime, session, size in sorted(rows, reverse=True)[:40]:
        when = datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"{when}  {size/1024:>9.0f}K  {session}  {slug}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", help="session uuid (see --list)")
    parser.add_argument("--project", help="project slug; inferred when unambiguous")
    parser.add_argument("--out", type=Path, help="destination TRACE.md")
    parser.add_argument("--title", default="Agent Trace", help="H1 title")
    parser.add_argument("--max-result", type=int, default=None,
                        help="truncate tool results to N chars, marked inline")
    parser.add_argument("--copy-raw", action="store_true",
                        help="also copy the source JSONL next to --out")
    parser.add_argument("--allow-finding", action="append", default=[], metavar="FINDING",
                        help="acknowledge one exact finding string after reviewing it, e.g. "
                             "'turn 176 (tool input): assigned api key'. Repeatable. Any "
                             "finding not listed still blocks the export.")
    parser.add_argument("--allow-secrets", action="store_true",
                        help="blanket override; prefer --allow-finding, which cannot mask a "
                             "credential that appears somewhere you did not review")
    parser.add_argument("--list", action="store_true",
                        help="list sessions for this project only (see --project)")
    args = parser.parse_args()

    if args.list:
        return list_sessions(args.project)
    if not args.session or not args.out:
        parser.error("--session and --out are required unless --list")

    candidates = list(PROJECTS.glob(f"{args.project}/{args.session}.jsonl")) if args.project \
        else list(PROJECTS.glob(f"*/{args.session}.jsonl"))
    if not candidates:
        print(f"session {args.session} not found under {PROJECTS}", file=sys.stderr)
        return 2
    if len(candidates) > 1:
        print(f"ambiguous session; pass --project. matches: {candidates}", file=sys.stderr)
        return 2
    source = candidates[0]

    markdown, findings = build(load(source), args.title, args.session, source,
                               args.max_result)

    # One fingerprint may surface in several turns; collapse to first sighting.
    unique: dict[str, str] = {}
    for finding in findings:
        unique.setdefault(finding.split("  (first seen:")[0], finding)
    allowed = set(args.allow_finding)
    acknowledged = [v for k, v in unique.items() if k in allowed]
    stale = [a for a in args.allow_finding if a not in unique]
    blocking = [v for k, v in unique.items() if k not in allowed]

    if stale:
        # An acknowledgement that no longer matches anything means the turn
        # numbering moved. Silently accepting it would carry a stale review
        # forward onto a finding nobody looked at.
        print("REFUSING to export: these --allow-finding values matched nothing.",
              file=sys.stderr)
        for finding in stale:
            print(f"  - {finding}", file=sys.stderr)
        print("\nRe-run without them, review the current findings, then acknowledge those.",
              file=sys.stderr)
        return 4

    if blocking and not args.allow_secrets:
        print("REFUSING to export: credential-shaped strings found.", file=sys.stderr)
        for finding in blocking:
            print(f"  - {finding}", file=sys.stderr)
        print("\nIf the source is a real credential, rotate it and stop echoing it.",
              file=sys.stderr)
        print("If you have read the turn and it is a fixture or an example, acknowledge it:",
              file=sys.stderr)
        for finding in blocking:
            print(f"  --allow-finding {finding.split('  (first seen:')[0]!r}", file=sys.stderr)
        return 3

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"wrote {args.out} ({len(markdown)/1024:.0f}K)")

    if args.copy_raw:
        raw = args.out.with_suffix(".raw.jsonl")
        raw.write_bytes(source.read_bytes())
        print(f"wrote {raw} ({raw.stat().st_size/1024:.0f}K)")
    for finding in acknowledged:
        print(f"acknowledged after review: {finding}", file=sys.stderr)
    if blocking and args.allow_secrets:
        print(f"WARNING: --allow-secrets waved through {len(blocking)} unreviewed match(es)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
