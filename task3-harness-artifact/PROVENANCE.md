# Provenance — internal record, not part of the submitted package

Answers review item `surface:8.5` (prove source identity and real use).

## Identity

| | |
|---|---|
| Source repository | `nddev-it-com/rldyour-claudecode` (marketplace `rldyour-claudecode`, owner `github:rldyourmnd`) |
| Path in source | `plugins/rldyour-flow/references/reviewer-protocol.md` |
| Pinned commit | `33c91856e41c417487862dc20018e9af6b67054a` |
| Installed copy | `~/.claude/plugins/cache/rldyour-claudecode/rldyour-flow/1.7.14/references/reviewer-protocol.md` |
| SHA-256 (all three) | `f4f1424b2f5b75a62e7e9864d5cfd3a4150d16aee6760d270911abbb2e816e04` |
| Byte comparison | `cmp` clean: installed == submitted == published-at-pinned-commit |

Verified 2026-08-23T18:51Z. The published copy was fetched from the GitHub
contents API at the pinned commit, so the submitted file is provably the
published file, not a local edit.

## Real use

11 commits touch the file between 2026-05-07 and 2026-06-01, including
`a463f2f fix(flow): harden reviewer output transport per review-wave findings`
— the protocol revised by findings from its own review waves.

18 references invoke it inside the installed marketplace: all six reviewer
agents (`flow-architecture-review`, `flow-quality-review`,
`flow-consistency-review`, `flow-integration-review`,
`flow-verification-review`, `flow-security-review`) cite it as the contract
they follow, and both orchestrators (`ry-review`, `ry-start`) read it before
dispatching a wave.

## Known defects in the artifact, unfixed at time of writing

Both were raised by external review and both are confirmed. Neither can be
corrected in this directory: the submitted file must stay byte-identical to its
source, so the fix belongs upstream in the marketplace repository and then gets
re-copied. Awaiting authorisation to push there.

1. **The read-only claim is an overclaim.** The file argues reviewers are
   read-only because `Edit`, `Write` and `NotebookEdit` are absent from the
   allowlist, while `Bash` is present and unrestricted. Bash can modify, delete
   and exfiltrate, so read-only is false as a technical property. It holds only
   as a contract the reviewer is asked to honour. Fix: enforce it (path-validating
   report writer, disposable worktree, or post-run `git diff --exit-code`), or
   rename the property "source-preserving by reviewer contract".

2. **Two of four cited issue dispositions are wrong.** Verified against the
   GitHub API on 2026-08-23T18:51Z:

   | Issue | Artifact says | Actual |
   |---|---|---|
   | `#16789` | not planned | closed, `not_planned` — correct |
   | `#20531` | not planned | closed, **`completed`** |
   | `#23463` | not planned | closed, `not_planned` — correct |
   | `#26251` | has limitations | closed, **`duplicate`** |

   The engineering conclusion survives — the file-first transport is sound
   regardless of how upstream dispositioned the reports — but an artifact whose
   theme is evidence quality must not miscite its own evidence.
