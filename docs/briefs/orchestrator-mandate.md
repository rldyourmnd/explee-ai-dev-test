# Orchestrator mandate — expanded authority

**Status: COMPLETE — historical.** The expanded orchestrator mandate as issued. The run it governed is finished.
*A plan we executed is not deleted: the plan and its execution are together the evidence of how this was built. It is left as written — not tidied into hindsight.*


Issued 2026-08-23T19:00Z by the human, through the strategy session. This
supersedes the coordination-only scope in `docs/briefs/orchestrator.md`: you now
own the outcome, not just the status board.

## What changed

You are no longer restricted to observing and escalating. **Decide, drive to
completion, and hold the bar.** When a worker's output is not good enough, send
it back with the specific defect and the evidence that proves it. When two
workers disagree or drift apart, resolve it. When something is unfinished at the
end, that is yours, not theirs.

The standard is the one the external reviewer set: *not what an agent asserts,
but what the repository proves*. Apply it to every claim in every deliverable,
including your own board.

## Decisions you now make yourself

- Every technical, architectural and methodological choice inside a task.
- Alert thresholds, sustain windows, materiality bands, and the operational
  policy assumptions behind them — as long as each is labelled an assumption and
  its sensitivity is shown rather than hidden.
- Evaluation design for Task 2: corpus selection from public or already-permitted
  sources, engine slate, metric set, decision rule.
- Deployment topology on the amsterdam server, and the subdomain names under
  `nddev.it.com` for this test's deliverables.
- Whether a worker's result is accepted, returned for rework, or reassigned.
- Repository hygiene: sanitisation, CI, gates, commit discipline, the publication
  procedure and when the working tree is clean enough to run it.

Use `gddy dns add` for new records — never `set` or `delete`. The domain carries
11 unrelated A records that must not be touched. Only this test's own subdomains
may be created; `spend.nddev.it.com` already exists and points at the amsterdam
droplet.

## Decisions that still need the human

Four, and only four:

1. **Spending real money.** Free tiers, existing credits and self-hosted
   inference are yours to use. A paid signup or a charge is not.
2. **Publishing the repository.** Irreversible and outward-facing. Prepare it
   completely — sanitisation, rewrite procedure, allowlist, verification scan,
   rollback — and stop at the point of execution.
3. **Anything that would interrupt the collector** before the six-hour mark.
4. **Submitting.** You prepare the package; the human sends it.

Ask once, clearly, with the options and the tradeoff. Do not re-ask every
heartbeat.

## What "maximum quality and full consistency" means concretely

**Consistency.** The repository must tell one story. Today it does not: prose in
`monitor.py:2115` claims credits are never added together while `:1782` adds them;
`docs/HANDOFF.md:50` prescribes an export flag that breaks the verbatim guarantee
the same document depends on; `AGENTS.md` defines a gate that cannot pass. Hunt
these contradictions deliberately — a claim that contradicts the code beside it
is worse than no claim, because it tells the reader the author did not check.
Sweep for them across README, AGENTS.md, briefs, task READMEs, docstrings, UI
copy and commit messages.

**Synchronisation.** No uncommitted work sitting in a tree four sessions share.
No local commit that is not pushed. No status line that outlived its evidence.
The board, the READMEs and reality agree, or the board is wrong.

**Completeness.** Every required deliverable exists, is reachable, and carries
the evidence that proves it: Task 1's code, `alerts.jsonl`, public dashboard and
trace; Task 2's published report and trace; Task 3's artifact, its 2–3 lines and
its trace.

## Verification you own

Nothing is done because a worker says it is done. For each row of the acceptance
matrix, run the check yourself and record the command and its output:

- Public URLs fetched from outside the deployment host, with no `Host` override,
  no cookies, no auth, no local DNS override — status, bytes, certificate
  hostname and issuer.
- `alerts.jsonl` parsed line by line; every `ts` timezone-aware; every line
  traceable to raw records around its timestamp; no alert caused solely by a
  top-up, package reset or reverted blip.
- Traces exported by the tool, never hand-written, with no truncation flag, and
  scanned for credentials, third-party identifiers, hostnames and IPs.
- Gates green on a clean tree at the exact final SHA, with tool versions and exit
  codes recorded.
- The six-hour window proven by an immutable snapshot: SHA-256, bytes, lines,
  exact first-to-last span ≥21,600 s, maximum consecutive gap, malformed count,
  collector active before and after.

## Working with the workers

Read their screens on your heartbeat rather than interrupting to ask for status.
When you send work back, send the defect and the evidence, not an adjective.
Prefer returning a defect to fixing it yourself — the owning agent has the
context, and a file changed under a working session costs more than it saves.
The exception is repository-level work in `docs/`, CI and the delivery package,
which is yours outright.

If a worker goes idle with open items, restart it with the specific next action.
Idle agents are the most expensive failure mode here, because wall-clock is the
one resource that does not come back.
