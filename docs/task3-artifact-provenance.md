# Task 3 artifact provenance — internal record, not part of the submitted package

The submission is one file plus 2-3 lines. This record and
`docs/task3-trace-quarantine.md` are working history and must be excluded by the
packaging step.

## Identity

| | |
|---|---|
| Artifact | `plugins/rldyour-serena-mcp/agents/flow-memory-sync.md` |
| Source repository | `nddev-it-com/rldyour-claudecode` (marketplace `rldyour-claudecode`) |
| Pinned commit | `e9879c212419992bda313c3725d615699f87a4c2` |
| SHA-256 (submitted and published) | `a16009988b189413be382077…` |
| Byte comparison | `cmp` clean: submitted == published-at-pinned-commit |

Verified 2026-08-24 by fetching the published blob from the GitHub contents API
at the pinned commit rather than trusting any local copy.

**The installed copy is deliberately not part of that comparison right now.**
`~/.claude/plugins/cache/.../1.7.14/agents/flow-memory-sync.md` still hashes
`26d0ed17…`, the pre-fix content, because the marketplace cache pins v1.7.14 and
the correction landed after it. Submitted matches the source of truth; the cache
catches up on the next plugin update. Claiming a three-way match today would be
false, and this file exists to be checkable.

Earlier this chain read installed == submitted == published at `26d0ed17…`
against commit `e2573dd`. That was true when written, and is superseded by the
upstream correction below.

## Real use

Dispatched by name from `rldyour-serena-mcp/hooks/stop_memory_sync.sh`, the
plugin's Stop hook — the agent runs because a hook fires it, not because a
document mentions it. 11 commits of history, 2026-05-08 → 2026-06-25.

## Why the selection changed

An earlier pass selected `rldyour-flow/references/reviewer-protocol.md`. A fresh
session re-ran the comparison and rejected it on verified grounds: of the four
GitHub issues it cites, `#20531` is closed as `completed` (not "not planned") and
`#26251` is closed as `duplicate`. Two of four citations are wrong in a file
whose entire subject is evidence discipline, and the submitted copy must stay
byte-identical to the published source, so the defect cannot be corrected inside
the submission. It is also a reference document: no trigger, no correction loop,
no stop condition of its own.

That earlier provenance chain was equally solid — three copies agreeing on
`f4f1424b…`, 11 commits, 18 references. Provenance was never the reason for the
change; the miscitations were.

## Upstream correction, 2026-08-24 (`e9879c2`)

External review found the artifact repeating the enforcement overclaim that
disqualified the previous candidate: it said "no general write access" and
"read-only on code" while its allowlist carries unrestricted `Bash`, and step 6
runs a helper script through it. Removing `Edit`/`Write`/`NotebookEdit` closes
those paths in the runtime, but a general shell is not bounded by which tool
names are absent.

Fixed at source rather than in the submitted copy, which must stay byte-identical.
Agent frontmatter has no per-command granularity, so the property cannot be
enforced at that layer; it is now described as what it is — source-preserving by
contract, allowlist enforcing part and discipline the rest — and modifying the
project tree through `Bash` is named as forbidden. The repository's own
`validate_agent_tools.py` and `validate_contract.py` pass on the change.

## Known limits of the chosen artifact

Steps 1 and 6 of 7 call `serena_memory_state.py` and
`commit_serena_knowledge.sh`, which ship in the same plugin but are not in the
submitted file. A reader can follow the agent's logic without them, but cannot
independently evaluate what `is_current` returns. This is stated in the README
rather than left for a reader to discover.

## Verification log — real command output

The reviewer cannot execute anything, so the commands and their actual
output are recorded here rather than summarised. Re-runnable as written.

```
Run at: 2026-08-23T21:16Z   repo HEAD: d020288

$ ls -1 task3-harness-artifact/
flow-memory-sync.md
README.md
TRACE.md

$ shasum -a 256 task3-harness-artifact/flow-memory-sync.md
a16009988b189413be382077b7859d581c638be9a5464efb31f173e4bc6693aa  task3-harness-artifact/flow-memory-sync.md

$ gh api .../flow-memory-sync.md?ref=e9879c2... | base64 -d | shasum -a 256   # published blob
a16009988b189413be382077b7859d581c638be9a5464efb31f173e4bc6693aa  -

$ gh api repos/nddev-it-com/rldyour-claudecode/commits/main --jq .sha   # fix is on default branch
e9879c212419992bda313c3725d615699f87a4c2
$ uv run --with pytest pytest tests/ -q | tail -1
293 passed in 20.43s

$ ruff check .
All checks passed!

$ uv run --with pyright --with pytest --with httpx pyright | tail -1
0 errors, 0 warnings, 0 informations

$ uv run tools/export_trace.py --session 9502fd71-... --submission  # then cmp with the shipped trace
wrote /tmp/s.md (89K)
cmp: shipped trace is byte-identical to a submission-mode re-export

$ scans on task3-harness-artifact/TRACE.md
IPv4 addresses:        0
SSH config lines:      2  (both are the session's own scan output reporting 0)
foreign project slugs: 0
truncation markers:    0
```

Two readings of that log that would be wrong without saying so:

- **`pyright: 0 errors` is not full coverage.** `pyrightconfig.json` excludes
  `tests/test_task2_bootstrap.py`, `test_task2_metrics.py` and
  `test_task2_reference.py`. Those files are hidden from the checker, not fixed.
  The zero is real for everything the checker looks at, and the checker has been
  told to look away from three files.
- **`SSH config lines: 2` is not a leak.** Both matches are the session's own
  scan output — the literal lines `HostName lines: 0` and
  `HostName (anchored): 0` — which the gate's own pattern matches. Printed in
  full above rather than characterised, so a reader can judge instead of trusting.
