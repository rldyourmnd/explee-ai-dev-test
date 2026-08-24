# Claude Code instructions

**`AGENTS.md` in the repository root is the single source of the working rules**
for every agent in this repository — the collector rule, secret handling,
enumeration hazards, trace integrity, evidence standards, time and units, pane
messaging, and the verification gates.

This file deliberately does not restate them. Two instruction files carrying the
same rules drift apart, and a rule that contradicts its twin is worse than one
that lives in a single place — that is the exact defect class this repository has
been fighting all run.

Claude Code specifics, which are the only things not covered there:

- Pane messaging goes through `tools/cmux_send.sh surface:N "text"`. Never
  hand-roll `cmux send` plus `send-key`: the Enter races the paste, the message
  sits unsent, and the sender never learns.
- The four gates, run before every push, all exit codes checked:

  ```bash
  uv run --with 'pytest==8.3.4' pytest tests/ -q
  uv run --with 'ruff==0.15.17' ruff check .        # pinned: unpinned checks a different ruleset
  uv run --with pyright==1.1.411 --with pytest==8.3.4 --with httpx pyright  # pinned, same reason as ruff
  uv run tools/repo_checks.py consistency
  ```

- **Every pane shares one working tree and one branch.** A commit cannot be held
  locally: the next agent to push carries yours to `origin` with it, whether or
  not you were ready. This was learned by promising the owner that a commit was
  being held back and finding it already public, pushed by another pane's commit
  landing on top of it. If something genuinely must not ship yet, it cannot be
  committed to `main` — say so rather than promising a hold the tree cannot give.

- `docs/TASK.md` is the verbatim task and outranks every paraphrase in this
  repository, including this file.
