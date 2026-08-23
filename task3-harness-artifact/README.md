# reviewer-protocol.md

Lives at `plugins/rldyour-flow/references/reviewer-protocol.md` in my Claude Code
plugin marketplace (`rldyour-claudecode`), installed under `~/.claude/plugins`; it is
the contract my `/ry-review` wave loads before fanning out.

It defines how six read-only reviewer subagents run in parallel: what a finding must
carry (severity, confidence, location, evidence, impact, fix, disposition), and a
file-first output transport — full report to disk, ≤4 KB summary back to the parent —
so a review wave cannot overflow the orchestrator's context and lose its own findings.
