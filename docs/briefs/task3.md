# Brief — Task 3: Your best harness artifact

You own Task 3 end to end. This session is one task, one trace: everything you
do here becomes `task3-harness-artifact/TRACE.md`, exported verbatim at the end.

## Read first

`AGENTS.md` — rules 2 (secrets) and 3 (do not enumerate unrelated
infrastructure) are the ones that will bite on this task specifically, because
you will be reading a personal harness that also touches unrelated client work.

## The ask, verbatim from the employer

> Attach the one harness artifact you are proudest of: a skill, a CLAUDE.md /
> AGENTS.md, a slash command, a prompt, a hook — whatever you actually use to
> make your work with AI agents better. One file, plus 2-3 lines on where it
> lives and what it does. This is a window into how you work day to day — taste
> and maturity matter more than size.

Deliverable: **one file**, plus 2–3 lines. Nothing else. The trace is what shows
how the choice was made.

## What you are actually doing

Selecting, not authoring. The artifact must be something already in daily use.
A file written for this test would be the wrong answer even if it read well —
the employer is looking for evidence of how the human already works.

## Inventory the real harness

The operator's harness lives across a local Claude Code configuration and a set
of published plugins. Start from what is installed and active, then trace each
back to its source repository:

- `~/.claude/` — settings, skills, agents, commands, hooks, plugin config.
- The `rldyour-*` plugin family (flow, rules, explore, security, design,
  orchestrator, browser, lsps, serena-mcp, mcps) — find where these are defined
  on disk and on GitHub under the `rldyourmnd` account.
- `gh repo list rldyourmnd` and `gh search code` scoped to that owner, for
  harness files that are not installed locally.

Build a real inventory before judging anything: path, type, size, what it does,
and evidence that it is actually used (git history, recency, whether it is wired
into settings, whether other files reference it).

## Judge on these

| Quality | How it shows up |
|---|---|
| Real daily use | Exists in the working harness with history behind it |
| Clear trigger | Unambiguous about when the agent must use it |
| Context acquisition | Makes the agent establish state before acting |
| Delegation | Has rules for handing independent work to subagents |
| Evidence gates | Conclusions require executable proof, not assertion |
| Correction loop | Defines what happens when verification fails |
| Stop conditions | Cannot declare success without evidence |
| Output contract | Result has a defined shape |
| Security | No secrets, no destructive defaults, no unbounded actions |
| Taste | As short as it can be while still complete |

Weak candidates, for calibration: a generic "write clean code" prompt, a giant
policy dump, a file that only works alongside ten unpublished internal skills,
anything without a verification loop.

## Hard constraints on the artifact you pick

- **Self-contained.** It must be readable and meaningful as a single file to
  someone with no access to the rest of the harness. If it hard-depends on
  private siblings, either pick another or verify the dependency is explained
  in-file. Check this by reading it as a stranger would.
- **No secrets, no private URLs, no client or project names, no internal
  hostnames or IPs.** This file is published to a third party. Grep it.
- Confirm it is not machine-generated boilerplate.

## Constraint on how you search

Rule 3 applies with force here. The harness sits next to unrelated client work,
and this trace is published verbatim to a third party. Do not `ls` the whole
`Developer/` tree, do not dump `~/.ssh/config`, do not print files belonging to
unrelated projects. Scope every search to harness paths and to the `rldyourmnd`
GitHub account. If a command would emit unrelated client names, narrow it first.

Before finishing, scan your own working area:

```bash
grep -oE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' task3-harness-artifact/*.md | sort -u
grep -c HostName task3-harness-artifact/*.md          # must be 0
```

## Deliverable shape

```
task3-harness-artifact/
├── <the-artifact-file>      the real file, copied verbatim from where it lives
├── README.md                the 2-3 lines: where it lives, what it does
└── TRACE.md                 exported at the end
```

Write the comparison that led to the choice into the README only if it stays
within a few lines — the employer asked for 2–3 lines, and padding it out is
itself a taste signal. The reasoning belongs in the trace.

## Definition of done

- A real, in-use artifact selected against a written inventory of alternatives.
- The file is verbatim from its source, self-contained, and clean of secrets and
  third-party identifiers.
- 2–3 lines stating where it lives and what it does.
- The trace shows the comparison, including candidates you rejected and why.

Do not touch `task1-*` or `task2-*`. Report to the orchestrator when done or
blocked.
