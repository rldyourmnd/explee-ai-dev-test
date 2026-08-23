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
  uv run --with pytest pytest tests/ -q
  uv run --with 'ruff==0.15.17' ruff check .        # pinned: unpinned checks a different ruleset
  uv run --with pyright --with pytest --with httpx pyright
  uv run tools/repo_checks.py consistency
  ```

- `docs/TASK.md` is the verbatim task and outranks every paraphrase in this
  repository, including this file.
