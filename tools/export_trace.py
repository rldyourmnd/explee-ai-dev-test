# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export a Claude Code session to a verbatim TRACE.md.

The employer asked for the REAL conversation, so this renders every user and
assistant turn in order, including reasoning blocks, tool calls with their full
inputs, and tool results. Nothing is paraphrased and nothing is dropped.

That claim is enforced, not asserted. Credentials, truncated tool results,
malformed JSONL lines, undecodable bytes and omitted image blocks all abort the
export and name what would have been lost, because a trace whose header claims
nothing was dropped while content is missing is worse than no trace: silently
rewriting the transcript would break the verbatim guarantee that makes it worth
reading, and disclosing a loss in a footnote does not make the document
verbatim either. --allow-lossy renders a damaged log anyway and stamps the
header so the file never claims to be something it is not.

Excision is the one permitted modification, and it is deliberately not
redaction. Redaction matches content and deletes whatever the pattern hit: the
operation is unreproducible, its extent is unknowable to a reader, and a
confidentiality removal is indistinguishable from deleting something
inconvenient. --excise instead addresses a named unit - one tool result, by turn
number or tool-call id - removes it whole, and has the tool state in place what
was removed, what produced it, why, and how many lines went. A reader sees a
complete transcript with a stated, countable, addressable hole rather than a
document that has been quietly rewritten. The whole result goes, never the
matching lines inside it: removing 4 names from a 52-line listing would leave 48
lines of an enumeration that should not have been run, and invite the question
of what the other 48 held. Messages, reasoning, corrections and failed attempts
are never touched.

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

# Whitelist rather than a fall-through chain: a block type this tool has never
# seen must be reported as lost, not skipped. Add a type here only together with
# the branch that renders it.
SUPPORTED_BLOCKS = frozenset({"text", "thinking", "tool_use", "tool_result"})

# Calls that enumerate things outside the current project. Content matching
# cannot close this class: a session or container listing prints bare names, so
# there is no pattern to write until after the name has leaked. What the
# exporter does know is which command produced each tool result, and an
# enumerating command is suspect whatever its output happens to look like.
#
# This is a list of known enumerators, not a proof of completeness - the next
# one will be a command nobody here has run yet. Deliberately narrow: it targets
# calls that cross a project boundary, not ordinary listing inside this project,
# because a guard that fires on every `ls` gets switched off.
# Anchored to a command position - start of line, or after a shell separator -
# so the verb has to be the thing being RUN. Matching these words anywhere in
# the payload flagged `grep "max_containers" modal_app/*.py`, which lists
# nothing, and a guard that fires on a grep of your own source is a guard people
# route around.
_CMD = r"(?:^|[;&|]\s*|\$\(\s*)"
ENUMERATING_CALLS: list[tuple[str, re.Pattern[str]]] = [
    ("session listing", re.compile(_CMD + r"(?:cmux\s+(?:list|ls)\b|\S*list-sessions\b)")),
    # export_trace --list is NOT here: it is project-scoped by construction, and
    # it is the fix for the original unscoped listing. Only pointing it at
    # another project enumerates anything.
    ("project listing", re.compile(r"--project(?:=|\s+)\S+|" + _CMD + r"ls\s+[^|;]*\.claude/projects")),
    ("container listing", re.compile(_CMD + r"(?:docker\s+(?:ps|container\s+ls)\b|"
                                            r"modal\s+app\s+list\b)")),
    ("repository listing", re.compile(_CMD + r"gh\s+(?:repo\s+list|search\s+repos)\b")),
    ("host configuration", re.compile(r"[^|;]*\.ssh/config|\bknown_hosts\b")),
    # Only when the listing targets the parent itself. `ls ~/Developer` shows
    # every project on the machine; `ls -d ~/Developer/org/one-project` checks
    # that one path exists and enumerates nothing, and flagging it would train
    # the operator to wave the guard through.
    ("home directory listing",
     re.compile(_CMD + r"ls\b(?![^|;]*\s-\w*d\b)[^|;]*~/(?:Developer|Projects|src|work)/?(?=[\s;|\"']|\\n|$)")),
]

# Fields carrying what was actually executed. A Bash `description` is prose the
# agent wrote about the call; scanning it flagged calls whose description merely
# mentioned containers or listing. Provenance is the command, not the caption.
COMMAND_FIELDS = ("command", "query", "cmd", "script")


def command_text(payload: str) -> str:
    """The executed part of a tool input, without the agent's own prose."""
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return payload
    if not isinstance(parsed, dict):
        return payload
    parts = [str(parsed[f]) for f in COMMAND_FIELDS if isinstance(parsed.get(f), str)]
    return "\n".join(parts) if parts else ""


def enumerating_reason(tool_name: str, payload: str) -> str | None:
    """Name the enumeration class of a call, or None if it does not enumerate."""
    if tool_name == "ListAgents":
        return "session listing"
    command = command_text(payload)
    # `--help` prints a tool's documentation. The exporter's own help text
    # describes --list, which is not the same as having listed anything.
    if re.search(r"(?:^|\s)--help\b", command):
        return None
    for reason, pattern in ENUMERATING_CALLS:
        if pattern.search(command):
            return reason
    return None


def load(path: Path, losses: list[str] | None = None) -> list[dict]:
    """Parse a session log, recording anything that could not be rendered.

    Both failure modes here used to be silent: undecodable bytes became U+FFFD
    via errors="replace", and a malformed line was skipped by the bare continue.
    Either one produces a trace that is missing content while the header still
    claims nothing was dropped. They are recorded now, and `main` refuses to
    write a trace when the list is non-empty.
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        if losses is None:
            raise
        losses.append(f"invalid UTF-8 in {path.name} at byte {exc.start}; "
                      f"decoded with replacement characters")
        text = raw.decode("utf-8", errors="replace")

    records = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if losses is not None:
                losses.append(f"malformed JSON on line {lineno} of {path.name}: {exc.msg}")
            continue
    return records


def fence(text: str, lang: str = "") -> str:
    """Wrap in a fence long enough to survive fences inside the payload."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    bar = "`" * max(3, longest + 1)
    return f"{bar}{lang}\n{text}\n{bar}"


def render_tool_result(content, losses: list[str] | None = None) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    if losses is not None:
                        losses.append("image block omitted from markdown "
                                      "(present in raw JSONL; export with --copy-raw)")
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


# A Claude Code project slug is an absolute path with the separators replaced by
# dashes, so any slug for a project other than the one being exported names
# somebody else's directory tree. That is the leak that killed two traces this
# run, and it is not a credential, so the secret scanner never saw it.
#
# A candidate needs a known root and at least two segments after it. That alone
# still matches ordinary hyphenated prose such as "-home-page-hero", so a match
# is only treated as foreign when it either sits under the same root and user as
# the project being exported (the realistic case - another project belonging to
# this operator, which is what leaked) or is deep enough that prose is an
# implausible explanation.
#
# Roots are enumerated rather than derived, because the permitted slug cannot
# say what another machine's home directory is called. A slug under an unusual
# root, or a shallow one belonging to a different user, is missed. That is a
# stated limit, not a silent one: this check narrows the hazard, it does not
# eliminate it, and the manual scan in AGENTS.md rule 3 stays.
FOREIGN_SLUG = re.compile(
    r"(?<![A-Za-z0-9._-])-(?:Users|home|root)-[A-Za-z0-9._]+(?:-[A-Za-z0-9._]+)+")
MIN_PROSE_IMPLAUSIBLE_SEGMENTS = 4  # root + user + dir + project


def scan_foreign_slugs(text: str, permitted: str | None) -> list[str]:
    """Report project slugs that are not the project being exported.

    `permitted` comes from the session file's own parent directory, never from
    listing the projects directory: enumerating it to build an allowlist would
    reproduce, inside this check, the exact defect the check exists to catch.
    """
    if not permitted:
        return []
    # "-Users-alice-work-thing" -> "-Users-alice": same machine, same account.
    home = "-".join(permitted.split("-")[:3])
    found: list[str] = []
    for match in FOREIGN_SLUG.finditer(text):
        # A slug written in prose collects the sentence's punctuation. Without
        # this the project's OWN slug followed by a full stop compares unequal
        # to `permitted` and reports as foreign - which would block every trace
        # this repository ever exports, since its own slug appears in paths,
        # in --list output and in the AGENTS.md rule-3 scan itself.
        slug = match.group(0).rstrip("._-")
        # A prefix of the permitted slug is the same project named shorter, not
        # a different one.
        if slug == permitted or permitted.startswith(slug):
            continue
        same_account = slug.startswith(home + "-")
        deep = len(slug.split("-")) - 1 >= MIN_PROSE_IMPLAUSIBLE_SEGMENTS
        if not (same_account or deep):
            continue
        ident = f"foreign project slug: {slug}"
        if ident not in found:
            found.append(ident)
    return found


def scan_leaks(text: str, permitted: str | None = None) -> list[str]:
    """Everything that must never reach a published trace: secrets, then slugs."""
    return scan_secrets(text) + scan_foreign_slugs(text, permitted)


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


DEFAULT_EXCISE_REASON = "it enumerated unrelated projects"


def excision_marker(turn: int, tool_use_id: str | None, tool_name: str | None,
                    removed_lines: int, reason: str) -> str:
    """The replacement text for an excised tool result.

    Generated here and nowhere else. A marker a human could type is a marker a
    reader has to take on trust, and the whole point of documenting an excision
    rather than withholding a trace is that the reader does not have to.
    """
    origin = f"`{tool_name}`" if tool_name else "a tool call"
    ident = f" (`{tool_use_id}`)" if tool_use_id else ""
    return (f"> **[EXPORTER] Tool result removed.** The result of {origin}{ident} at turn "
            f"{turn} was removed by `tools/export_trace.py --excise`, because {reason}. "
            f"**{removed_lines} line{'s' if removed_lines != 1 else ''} removed.** Everything "
            f"else in this trace is verbatim, and the unedited session log retains this block.")


def build(records: list[dict], title: str, session_id: str, source: Path,
          max_result: int | None, losses: list[str] | None = None,
          permitted_slug: str | None = None, excise: set[str] | None = None,
          excise_reason: str = DEFAULT_EXCISE_REASON) -> tuple[str, list[str]]:
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
    excise = excise or set()
    excised: list[str] = []

    # tool_use_id -> (tool name, input payload). A tool_result carries only the
    # id of the call that produced it, so provenance has to be resolved before
    # the render loop reaches the result.
    origins: dict[str, tuple[str, str]] = {}
    for record in turns:
        blocks = record.get("message", {}).get("content")
        for block in blocks if isinstance(blocks, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                origins[str(block.get("id"))] = (
                    str(block.get("name", "")),
                    json.dumps(block.get("input", {}), ensure_ascii=False))

    for index, record in enumerate(turns, start=1):
        message = record["message"]
        role = record["type"]
        label = ROLE_LABEL.get(role) or str(role)
        if record.get("isSidechain"):
            label += " (subagent)"
        out.append(f"## [{index}] {label} · {human_ts(ts_of(record))}")
        out.append("")

        content = message.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            # None, a number, a dict - anything the schema did not promise. The
            # old code substituted an empty list, so the turn rendered as a
            # heading with no body and nothing said so.
            if losses is not None:
                losses.append(f"turn {index}: message.content was "
                              f"{type(content).__name__}, not str or list; no blocks rendered")
            content = []

        for block in content:
            if not isinstance(block, dict):
                if losses is not None:
                    losses.append(f"turn {index}: content block was "
                                  f"{type(block).__name__}, not an object; skipped")
                continue
            kind = block.get("type")
            if kind not in SUPPORTED_BLOCKS:
                # Claude Code gains block types over time. An unknown one used to
                # fall off the end of this chain unrendered, leaving a header that
                # claims nothing was dropped - the exact failure this tool exists
                # to prevent. Unknown means lost until someone teaches it the type.
                if losses is not None:
                    losses.append(f"turn {index}: unsupported content block type "
                                  f"{kind!r}; not rendered")
                continue

            if kind == "text":
                body = block.get("text", "")
                findings += [f"{n}  (first seen: turn {index}, text)" for n in scan_leaks(body, permitted_slug)]
                out += [body, ""]

            elif kind == "thinking":
                body = block.get("thinking", "")
                findings += [f"{n}  (first seen: turn {index}, thinking)" for n in scan_leaks(body, permitted_slug)]
                out += ["<details><summary>Reasoning</summary>", "", fence(body), "",
                        "</details>", ""]

            elif kind == "tool_use":
                payload = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
                findings += [f"{n}  (first seen: turn {index}, tool input)" for n in scan_leaks(payload, permitted_slug)]
                out += [f"**Tool call — `{block.get('name')}`**", "",
                        fence(payload, "json"), ""]

            elif kind == "tool_result":
                use_id = str(block.get("tool_use_id") or "")
                tool_name, payload = origins.get(use_id, ("", ""))

                # Excision runs before the scanners on purpose: removed content
                # must stop blocking the export, otherwise excising the leak
                # still leaves the finding that made it necessary.
                if str(index) in excise or (use_id and use_id in excise):
                    removed = render_tool_result(block.get("content"))
                    n_lines = len(removed.splitlines())
                    out += [excision_marker(index, use_id or None, tool_name or None,
                                            n_lines, excise_reason), ""]
                    excised.append(f"turn {index}"
                                   + (f" ({tool_name})" if tool_name else "")
                                   + f", {n_lines} lines")
                    continue

                body = render_tool_result(block.get("content"), losses)
                findings += [f"{n}  (first seen: turn {index}, tool result)" for n in scan_leaks(body, permitted_slug)]
                reason = enumerating_reason(tool_name, payload) if use_id else None
                if reason:
                    findings.append(
                        f"enumerating call ({reason}): result of "
                        f"{tool_name or 'a tool call'}  (first seen: turn {index}, tool result)")
                if max_result is not None and len(body) > max_result:
                    dropped = len(body) - max_result
                    if losses is not None:
                        losses.append(f"turn {index}: {dropped} characters of tool "
                                      f"result truncated by --max-result")
                    body = (body[:max_result]
                            + f"\n\n[... {dropped} characters truncated by "
                              f"--max-result; full output is in the raw session JSONL ...]")
                status = " (error)" if block.get("is_error") else ""
                out += [f"**Tool result{status}**", "", fence(body), ""]

        out.append("---")
        out.append("")

    # The header promises a verbatim render. If anything was lost, that promise
    # is retracted at the top of the file, not footnoted where the loss happened
    # - a reader decides whether to trust the document before reading it.
    if excised:
        notice = [f"> **Verbatim except for {len(excised)} documented "
                  f"excision{'s' if len(excised) != 1 else ''}.** A tool result was removed "
                  f"at each point listed below, because {excise_reason}. Each removal is "
                  f"marked in place by the exporter, with the number of lines removed:", ""]
        notice += [f"> - {item}" for item in excised]
        notice += ["", "> Nothing else was altered. The unedited session log is the "
                   "authoritative record.", ""]
        out[out.index("---"):out.index("---")] = notice

    if losses:
        notice = ["> **This export is not verbatim.** The following content "
                  "could not be rendered losslessly:", ""]
        notice += [f"> - {loss}" for loss in dict.fromkeys(losses)]
        notice += ["", "> The raw session JSONL is the authoritative record.", ""]
        out[out.index("---"):out.index("---")] = notice

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
    parser.add_argument("--allow-lossy", action="store_true",
                        help="write the trace even though content was truncated, skipped "
                             "or replaced; the header declares the export non-verbatim")
    parser.add_argument("--excise", action="append", default=[], metavar="TURN|TOOL_USE_ID",
                        help="remove one tool result and leave a generated marker naming the "
                             "reason and the number of lines removed. Addressed by turn number "
                             "or tool-call id - never by matching content, so it cannot take "
                             "more than intended. Repeatable, and permitted in --submission.")
    parser.add_argument("--excise-reason", default=DEFAULT_EXCISE_REASON,
                        help="why the excised results were removed; appears in the generated "
                             "marker and in the header notice")
    parser.add_argument("--submission", action="store_true",
                        help="export for publication: every override is refused, so the "
                             "result is verbatim and clean or it does not exist")
    parser.add_argument("--list", action="store_true",
                        help="list sessions for this project only (see --project)")
    args = parser.parse_args()

    # One flag the operator can point at, instead of remembering which overrides
    # are safe today. A submission export has no valid reason to truncate, to
    # wave through a credential, or to acknowledge a foreign identifier: if any
    # of those is needed, the fix belongs in the session, not in the flags.
    if args.submission:
        forbidden = [name for name, used in (
            ("--allow-lossy", args.allow_lossy),
            ("--allow-secrets", args.allow_secrets),
            ("--allow-finding", bool(args.allow_finding)),
            ("--max-result", args.max_result is not None),
        ) if used]
        # --excise is absent from that list deliberately. It is the one
        # modification that documents itself: the marker is generated here, says
        # what went and how much, and the header stops claiming a plain verbatim
        # export. Withholding a whole trace to avoid one contaminated block is a
        # worse outcome than publishing it with the block visibly removed.
        if forbidden:
            print(f"--submission forbids {', '.join(forbidden)}.", file=sys.stderr)
            print("A published trace is verbatim and clean, or it is not published.",
                  file=sys.stderr)
            return 5

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

    losses: list[str] = []
    # Derived from the session file's own location, never by listing PROJECTS:
    # enumerating the projects directory to build an allowlist would reproduce
    # the --list defect inside the fix for it.
    permitted_slug = source.parent.name

    markdown, findings = build(load(source, losses), args.title, args.session, source,
                               args.max_result, losses, permitted_slug,
                               set(args.excise), args.excise_reason)

    # Fail closed on any lossy path. A trace whose header says "nothing was
    # dropped" while a tool result was truncated, a malformed line was skipped,
    # or bytes were replaced is not verbatim, and disclosing the truncation in
    # the body does not make it verbatim either. --allow-lossy exists so the
    # operator can still get a readable rendering of a damaged log, and it
    # stamps the header so the resulting file never claims more than it is.
    if losses and not args.allow_lossy:
        print(f"refusing to write {args.out}: export would not be verbatim",
              file=sys.stderr)
        for loss in dict.fromkeys(losses):
            print(f"  - {loss}", file=sys.stderr)
        print("\nfix the source of the loss, or pass --allow-lossy to write a "
              "rendering that declares itself incomplete.", file=sys.stderr)
        return 3

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

    # --allow-secrets is scoped to credentials only. A synthetic key in a test
    # fixture is a routine thing to wave through; another client's directory name
    # is not, and one flag covering both meant acknowledging the first silently
    # acknowledged the second. Foreign slugs have no blanket override at all -
    # they can only be cleared one at a time with --allow-finding, after reading
    # the turn.
    waved = args.allow_secrets and not any(
        f.startswith("foreign project slug:") for f in blocking)
    if blocking and not waved:
        slugs = [f for f in blocking if f.startswith("foreign project slug:")]
        enums = [f for f in blocking if f.startswith("enumerating call")]
        creds = [f for f in blocking if f not in slugs and f not in enums]
        kinds = ", ".join(k for k in (
            "credential-shaped strings" if creds else "",
            "project names belonging to other work" if slugs else "",
            "results of calls that enumerate unrelated things" if enums else "") if k)
        print(f"REFUSING to export: {kinds} found.", file=sys.stderr)
        for finding in blocking:
            print(f"  - {finding}", file=sys.stderr)
        if creds:
            print("\nIf the source is a real credential, rotate it and stop echoing it.",
                  file=sys.stderr)
        if slugs:
            print("\nA project slug is a directory path belonging to unrelated work. Fix the "
                  "turn that produced it - narrow the command so it never reads outside this "
                  "project - rather than exporting and scrubbing afterwards.", file=sys.stderr)
            if args.allow_secrets:
                print("--allow-secrets does not cover project slugs, deliberately: waving "
                      "through a test credential must not also wave through somebody else's "
                      "directory name.", file=sys.stderr)
        if enums:
            print("\nA call that enumerates unrelated projects, sessions, containers or hosts "
                  "is flagged by what produced it, not by what it printed - a listing of bare "
                  "names has no pattern to match until after it leaks. Read the turn: if the "
                  "output names anything outside this project, remove it with "
                  "--excise <turn|tool_use_id>, which leaves a generated marker saying what "
                  "went and how many lines.", file=sys.stderr)
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
