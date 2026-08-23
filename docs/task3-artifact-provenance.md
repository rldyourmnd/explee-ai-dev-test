# Task 3 artifact provenance — internal record, not part of the submitted package

The submission is one file plus 2-3 lines. This record and
`docs/task3-trace-quarantine.md` are working history and must be excluded by the
packaging step.

## Identity

| | |
|---|---|
| Artifact | `plugins/rldyour-serena-mcp/agents/flow-memory-sync.md` |
| Source repository | `nddev-it-com/rldyour-claudecode` (marketplace `rldyour-claudecode`) |
| Pinned commit | `e2573ddaea43c1a06d92177e31ad3485354f10a9` |
| Installed copy | `~/.claude/plugins/cache/rldyour-claudecode/rldyour-serena-mcp/1.7.14/agents/flow-memory-sync.md` |
| SHA-256 (all three) | `26d0ed17324707e5ac020b0a…07a04` |
| Byte comparison | `cmp` clean: installed == submitted == published-at-pinned-commit |

Verified independently 2026-08-24, by fetching the published blob from the GitHub
contents API at the pinned commit rather than trusting the local cache.

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

## Known limits of the chosen artifact

Steps 1 and 6 of 7 call `serena_memory_state.py` and
`commit_serena_knowledge.sh`, which ship in the same plugin but are not in the
submitted file. A reader can follow the agent's logic without them, but cannot
independently evaluate what `is_current` returns. This is stated in the README
rather than left for a reader to discover.
