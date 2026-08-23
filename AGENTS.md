# Working rules for agents in this repository

## Non-negotiable

1. **Never stop the collector.** `explee-raw-sampler.service` on
   `server-nddev-amsterdam` has been capturing since T0 = 2026-08-23T16:14Z.
   The task requires ≥6 hours and the API has no history endpoint, so any
   interruption is unrecoverable. Check with
   `ssh server-nddev-amsterdam systemctl is-active explee-raw-sampler` before
   and after touching that host.

2. **Secrets only through environment variables, never echoed.** Traces are
   published verbatim, so a key printed once is a key published. Do not run
   `env`, do not `cat .env`, do not paste keys into prompts, do not log
   `Authorization` headers. `tools/export_trace.py` refuses to export when it
   finds a credential rather than redacting one, because redaction would break
   the verbatim guarantee.

3. **Do not enumerate unrelated infrastructure.** Traces are published
   verbatim to a third party, so anything a session reads becomes something the
   reader sees. Never dump `~/.ssh/config`, never `ls` the whole `Developer/`
   tree, never run `docker ps` on a host for reasons unrelated to this work.
   Touch `server-nddev-amsterdam` because it hosts this deliverable; do not
   touch or list anything else. Scan before publishing:

   ```bash
   grep -oE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' TRACE.md | sort -u
   grep -cE '^[[:space:]]*HostName[[:space:]]+[A-Za-z0-9_.-]+[[:space:]]*$' TRACE.md   # must be 0
   ```

   **Third revision, 19:36Z.** The anchored form still could not pass. A trace
   that quotes its own scan output starts a line with `HostName lines: 0`, which
   matches `HostName` followed by whitespace — so the Task 3 trace scored 2 on a
   file containing no SSH config at all. The gate now also requires the line to
   *end* in a single hostname-shaped token, which is what an SSH config line
   actually looks like and what a scan report never is. Verified: 0 on that
   trace, and still 2 on a fixture holding two real `HostName` lines.

   Three revisions of one gate is worth the paragraph. Each version was written
   to catch a real leak and each was tested only against the leak, never against
   a clean file that merely mentions the pattern. A gate needs both directions
   tested or it is a gate against the last incident, not against the class.

   The `HostName` pattern is anchored to the start of a line because that is
   what an SSH config block looks like. The older bare-word `grep -c HostName`
   could never reach 0 in a trace that quotes this rule, or that shows the scan
   being run — it flagged its own instructions. `HostName\s+\S+` has the same
   flaw: in `grep -c HostName TRACE.md` the filename is the non-space token.

   These two scans test for IPs and SSH config. They do not test for project or
   client names, and a trace that passes them is not thereby clean: on
   2026-08-23 an unscoped `--list` put 20 rows of an unrelated project's name
   into a task trace that passed both scans, and the trace was quarantined. A
   scan licenses a conclusion only about the pattern it matches. Before
   publishing, also confirm no foreign project slug appears:

   ```bash
   grep -oE '\-Users-[A-Za-z0-9-]+' TRACE.md | sort -u   # expect only this project
   ```

4. **Traces are exported, never written.** A TRACE.md is produced only by
   `tools/export_trace.py` from a real session log. Do not compose, summarise,
   tidy, or reorder a trace. Failed attempts and corrections stay in.

5. **Two traces were quarantined and are now deleted from the working tree.**
   `TRACE-orchestration.md` was produced before rule 3 existed and carried an SSH
   config dump and nine unrelated client IPs; the Task 3 trace carried a
   directory listing naming an unrelated client project. Both were first
   quarantined in place, then removed entirely at 18:52Z on the way to
   publication. **They still exist in git history**, which is why publication
   requires the history rewrite in `docs/ACCEPTANCE.md` and not merely a
   `git rm`. A deleted file and a purged file are different things, and only the
   second is safe to publish.

## Enumeration hazards — never list what you did not come to see

Three separate leaks in this run had one shape: **a tool's listing command
enumerated the whole machine or account, and the tool output landed verbatim in a
trace.**

1. `export_trace.py --list` globbed every project under `~/.claude/projects` and
   put an unrelated client's name into the Task 3 trace 20 times. That trace was
   quarantined and is now deleted.
2. The orchestration session listed SSH hosts and `Developer/` while choosing a
   deploy target, producing 9 third-party IPs and 16 `HostName` lines. That trace
   was quarantined and is now deleted.
3. `modal app list` enumerates the workspace and prints a deployed app belonging
   to an unrelated client.

Three for three. Assume the pattern is general, because it is: these commands are
*designed* to show everything you own, and a hiring-test trace is published
verbatim to strangers.

**Measured breadth of the tools on this machine** — run as counts only, never
printing names, so this document and the trace that produced it stay clean:

| Command | Reaches |
|---|---|
| `gh repo list` | 36 repositories |
| `systemctl list-units` | 69 services on the droplet |
| `doctl compute droplet list` | 8 droplets |
| `docker ps` | 8 containers |
| `modal app list` | the whole workspace |
| `gddy domain list` | the whole registrar account |

**Standing check, not a reminder.** This class has now bitten four times:
`export_trace.py --list`, the session-directory listing that contaminated the
first Task 3 trace, `modal app list`, and the `gh`/`doctl`/`gddy` listings
measured above. **Before a worker uses a tool that is new to this repository,
check its listing commands against this section.** A tool that can reach past
this project is a loaded gun pointed at a published trace.

**The rule.** In any session that will be exported, do not run a bare listing
command. Scope it to the object you already know you need
(`gh repo view <this-repo>`, `systemctl is-active explee-raw-sampler`,
`docker inspect explee-spend-monitor`), or pipe it to a count when you only need
to know how many. If you genuinely must enumerate, do it in a session that will
never be published, and carry only the single answer back.

The general form: **a command that answers a question you did not ask is a leak
waiting for an audience.** Redaction afterwards is not available, because a trace
that is edited is no longer verbatim.

## Coordinating panes — delivery is a claim, not an action

`cmux send` **types** text into a target pane's prompt. It does not submit it.
The text sits there, unsent, until something presses Enter — and a silent
non-delivery is indistinguishable from a delivered message unless you look.

Three steps, always:

```bash
cmux send --surface surface:N 'your message'
cmux send-key --surface surface:N Enter
cmux read-screen --surface surface:N --lines 8      # not optional
```

Reading the screen back is how you learn whether it landed. If your text is
still sitting at the prompt, it did not send — press Enter again. If the screen
shows `Press up to edit queued messages`, the recipient is mid-task and your
message is queued, which is fine and needs nothing.

This has already cost real wall-clock here: on 2026-08-23 two panes sat idle with
instructions unsubmitted in their buffers while the critical path waited.

**Two traps.** Never type into a pane showing an interactive menu or a selection
list — a keystroke can pick an option and wreck its state; press Escape first.
And never send fresh text into a buffer that already holds unsent text: `send`
appends, so you would submit a splice of two messages neither author wrote.
Press Enter on what is there instead.

The framing this repository uses everywhere else applies to messaging too:
**an unverified send is an assumption, and an assumption is not evidence.**

## Committing in a shared worktree

**Use `git commit -- <paths>`. Never `git add` then `git commit`.**

`git add` writes to an index every session in this worktree shares, so *any*
window between staging and committing lets another session's commit sweep your
staged files into its own. Narrowing what you stage shrinks the blast radius; it
does not close the window, because the window is the mechanism.

`git commit -- <paths>` commits working-tree content for those paths in one
operation with no staging step. No window, no shared state.

This bit three times on 2026-08-23: `7a90b2f` carried Task 1's monitor fixes
under *"Record Task 2 publication"*, `1282ad1` carried Task 1's polling-loop
tests under *"Task 2: power simulation"*, and one orchestrator change landed
under an unrelated exporter subject. Nothing was ever lost — what was lost is
**discoverability**, a rationale filed under a subject line nobody searching for
it will read. A correct commit with the wrong message is a defect in the history,
which is one of the artifacts being graded here.

## Evidence

Every claim in a deliverable is a hypothesis plus the data behind it. "The API
is flaky" is not a finding; "429 on `tremendous` and `findymail` in the same
poll cycle at 16:01Z, 2 of 15 providers" is. If something cannot be measured,
say so explicitly instead of estimating quietly — the top-up/spend ambiguity in
`README.md` is the worked example.

## Time

All timestamps are timezone-aware. This machine is UTC+5 (Asia/Almaty) and the
work is graded across timezones, so every emitted timestamp carries an explicit
offset or a `Z`. Never emit a naive local time.

## Units

Never sum across pay models or currencies. USD balance, GBP balance, package
credits, trailing spend and postpaid credit are five different things; a single
"total spend" number mixing them would be fiction. Aggregate only within a unit.

## Verification before delivery

```bash
uv run --with pytest pytest tests/ -q && uv run --with 'ruff==0.15.17' ruff check .
```
