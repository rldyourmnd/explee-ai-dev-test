# TRACE-task3-quarantined.md is not part of the submission

Same disposition as `TRACE-orchestration.md` (rule 5): it stays in this private
repository as working history and is excluded from what ships to the employer.

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

## Fixes worth making at the source

1. `--list` should require or infer `--project` and glob that slug only, instead
   of every project on the machine.
2. The exporter's refusal patterns cover credentials only. A trace that
   publishes verbatim also needs a foreign-identifier check - at minimum, project
   slugs under `~/.claude/projects/` other than the one being exported.
3. The `grep -c HostName` gate in `AGENTS.md` matches the bare word, so it can
   never reach 0 in a trace that quotes the rule. Matching `HostName\s+\S+`
   would test SSH config content rather than the word.

Not applied here: `tests/test_export_trace.py` is checked out modified by
another live session and these changes belong with it.
