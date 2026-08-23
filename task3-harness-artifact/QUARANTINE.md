# TRACE-task3-quarantined.md is not part of the submission

Same disposition as `TRACE-orchestration.md`. Both were first quarantined in
place, then removed from the working tree at 18:52Z on the way to publication.
The file this record describes therefore no longer exists beside it — **but it
still exists in git history**, so publication requires the history rewrite in
`docs/ACCEPTANCE.md`, not merely the deletion. A deleted file and a purged file
are different things (`AGENTS.md` rule 5).

## What happened

Turn 78 of the Task 3 session ran `uv run tools/export_trace.py --list`. That
flag globs `~/.claude/projects/*` and prints the 40 most recent sessions across
every project, so the tool result carried 20 rows naming an unrelated client
project. The trace publishes verbatim, so the leak is in the exported file at
lines 1971-1990.

## Why it was not re-exported instead

`export_trace.py` has no flag that excludes a turn or a single tool result.
`--max-result` truncates head-first (`body[:max_result]`, line 230) and the leak
is in row 1 of the result, so no value removes it without gutting every tool
result in the trace. `--allow-finding` / `--allow-secrets` only widen the
credential gate; they do not drop content. Hand-editing was rejected under rule
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
2. **Open.** The exporter's refusal patterns cover credentials only. A trace that
   publishes verbatim also needs a foreign-identifier check - at minimum, project
   slugs under `~/.claude/projects/` other than the one being exported. `AGENTS.md`
   now carries a manual slug scan, but manual is not the same as enforced, and the
   scan that caught this leak should live in the tool.
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
