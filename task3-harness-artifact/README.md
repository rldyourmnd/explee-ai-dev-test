# flow-memory-sync.md

**Where it lives:** `plugins/rldyour-serena-mcp/agents/flow-memory-sync.md` in my Claude Code plugin marketplace (`rldyour-claudecode`), installed under `~/.claude/plugins`; my Stop hook dispatches it by name after a task wave commits.

**What it does:** refreshes my project memory files, and its whole job is refusing to write anything it cannot prove: existing memory ranks *last* in the source-of-truth hierarchy, every claim is re-verified against code at HEAD and then kept, edited, deleted or demoted to "Known gaps", counts and SHAs are re-derived rather than carried over, and the only permitted output is a one-line JSON report.

**Tradeoff:** two of its seven steps call helper scripts that ship beside it, so it names its dependencies rather than standing entirely alone.
