# Task 3 trace quarantine — internal record, not part of the submitted package

Nothing is withheld from the submission: Task 3 ships a real, untruncated
`TRACE.md` from a genuine session, like every other task. This record covers an
earlier export that was quarantined and removed, and is kept because the
incident staying documented is the point. The packaging step must exclude it,
along with `docs/task3-artifact-provenance.md`.


The trace in question was exported as
`task3-harness-artifact/TRACE-task3-quarantined.md` and is no longer in the
working tree.

Disposition, same as `TRACE-orchestration.md`: quarantined in place, then
removed from the working tree at 18:52Z on the way to publication. **The content
is not gone.** It survives in git history and will until the `git filter-repo`
rewrite in `docs/ACCEPTANCE.md` (rows X.4 and X.8) is run — that step has been
written but not executed. A `git rm` is not a purge, and anyone reading this
file should not conclude otherwise: until the rewrite lands, `git log -p --all`
still contains every leaked line (`AGENTS.md` rule 5).

## What happened

Turn 78 of the Task 3 session ran `uv run tools/export_trace.py --list`. That
flag globs `~/.claude/projects/*` and prints the 40 most recent sessions across
every project, so the tool result carried 20 rows naming an unrelated client
project. The trace publishes verbatim, so the leak is in the exported file at
lines 1971-1990.

## Why it was not re-exported instead

`export_trace.py` has no flag that excludes a turn or a single tool result.
`--max-result` truncates head-first (the `body[:max_result]` slice in `build`;
no line number, because that pointer has gone stale twice already as the file
grew) and the leak is in row 1 of the result, so no value removes it without gutting
every tool result in the trace. `--allow-finding` / `--allow-secrets` only widen
the credential gate; they do not drop content. Since `ca27622` the point is
moot: `--max-result` is itself a lossy path and now refuses to write at all
without `--allow-lossy`. Hand-editing was rejected under rule
4: a tidied trace is worth less than a quarantined one.

## Why the scans passed

The two mandated scans returned 0 IPs and, on inspection, only self-referential
`HostName` hits from the scan commands themselves. Both results were correct.
Neither tested for project or client names, so they were never evidence that
the trace was clean of them. A passing scan licenses a conclusion only about
the patterns it actually matches.

## Fixes made at the source

1. **Done** (`d7c2b24`). `--list` lists one project, defaulting to the slug for
   the current directory, and its error path does not name the projects it found
   instead. Four regression tests, verified to fail against the old code.
2. **Done** (`1ee633e`). The exporter refused credentials only; the leak was a
   project slug, so the scanner never saw it. `scan_foreign_slugs` now fails the
   export closed on any project slug other than the one being exported, naming the
   slug and the turn. The permitted slug comes from the session file's own parent
   directory - listing the projects directory to build an allowlist would have
   reproduced the `--list` defect inside the fix for it. Validated against this
   very trace: it returns exactly one finding, the real leak, while this project's
   own slug in the same file is ignored. `--allow-secrets` deliberately does not
   cover slugs (`f21487f`): waving through a test credential must not wave through
   somebody else's directory name.
3. **Done** (`d7c2b24`). The `grep -c HostName` gate matched the bare word, so it
   flagged its own instructions and could never reach 0 in a trace quoting the
   rule. `HostName\s+\S+` was tried first and rejected: in
   `grep -c HostName TRACE.md` the filename is the non-space token, so prose
   still matched. The gate is anchored to `^\s*HostName\s+`, which is what SSH
   config looks like. Measured on this trace: 6 false alarms before, 0 after.

Separately, the lossy-export defect the external review found in the same tool
is closed (`ca27622`): truncation, malformed JSONL, undecodable bytes and
omitted image blocks now abort the export instead of producing a trace whose
header claims nothing was dropped.
