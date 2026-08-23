# Working rules for agents in this repository

## Non-negotiable

1. **Never stop the collector.** `explee-raw-sampler.service` on
   `server-nddev-amsterdam` has been capturing since T0 = 2026-08-23T16:14Z.
   The task requires ≥6 hours and the API has no history endpoint, so any
   interruption is unrecoverable. Check with
   `ssh server-nddev-amsterdam systemctl is-active explee-raw-sampler` before
   and after touching that host.

   **Nothing about the running system changes while the observation window is
   open.** Not the collector, and not the monitor deriving from it. Improvements
   are committed and tested but deployed only at a snapshot boundary. A restart
   is a risk taken against evidence that exists exactly once, and "it will
   probably be fine" is not a reason to take it. The consequence is that the
   deployed build sits behind the repository for stretches, and that gap is
   stated in `task1-spend-observability/README.md` rather than mistaken for
   drift.

   When derived state *is* dropped at such a boundary: **stop the container
   first, then delete, then start.** The running process holds the SQLite file
   open and its tail thread recreates it, so `rm` followed by `restart` leaves
   the new process resuming from an offset that should not exist — that mistake
   replayed 16 records where a full window was intended. And never detect
   "replay finished" by grepping the log for the serve banner: the previous
   run's banner is still there. Count `[replay]` lines before starting and wait
   for the count to rise. `tools/deploy_monitor.sh` encodes both.

   **Snapshots copy, never move, and verify by prefix.** The log is append-only
   and still being written, so hashing the host file and then copying it
   compares two different lengths and can never agree. Copy first, hash the
   copy, then ask the host for the digest of the same leading byte count.
   `tools/snapshot_window.py` does this and refuses to run at all if the
   collector is not active.

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

## Modal GPUs

The workspace plan allows **10 concurrent GPUs**, and exhausting them stops
every other session, not just yours. On 2026-08-23 a Task 2 function with
`max_containers=10` held all ten and the owner got a limit email.

Cap fan-out and run engines sequentially:

```python
@app.cls(gpu=["L4", "A10"], max_containers=4, scaledown_window=60, ...)
```

The arithmetic is why this costs nothing: an hour of audio in 30 s pieces takes
one L4 ten to twenty minutes, so four containers finish it in under five and ten
are no faster. Pick the smallest GPU that fits; an H100 finishes a 30 s clip no
sooner. The parameter names are `max_containers` and `scaledown_window`; the
older `concurrency_limit` and `container_idle_timeout` are gone.

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

## A text sweep over source is a code change

On 2026-08-23 an em-dash sweep — a presentation change — rewrote a `&mdash;`
placeholder inside a tuple assignment in `monitor.py`, producing
`lead, sub, cls = ",", ...`. It clobbered the loop's CSS-class variable. A
provider group with no projection would have rendered `<div class="card,">`
with the figure unbound.

**Pyright caught the unbound half. Nothing caught the clobbered half.** It stayed
invisible through every gate and only surfaced later, when card ranking happened
to introduce a variable named `lead`.

The lesson is not "be careful with `sed`". It is that a mechanical rewrite over
source can change **semantics** while looking like typography, and a type checker
only sees the damage that leaves a name unbound. Treat a presentation sweep over
code as a logic change: read the diff hunk by hunk, and diff the **rendered
output** before and after, not just the source.

The same shape has appeared twice more here. A redaction filter written with
`\b` on macOS `sed` matched nothing and printed the text it was meant to hide.
A `--max-result` flag truncated tool output while the generated header claimed
nothing had been dropped. In all three the tool reported success while doing the
opposite of its purpose.

## Check that the instrument honoured the conditions you asked for

A measurement is only evidence if the setup you requested is the setup that ran.

On 2026-08-23 a 390 px responsive check appeared to show real overflow: the
subtitle and a metadata line running off the right edge, cards missing their
right border. It was the instrument. Headless Chrome on macOS clamps the window
to a 500 px minimum, so `--window-size=390` **laid the page out at 500 and then
cropped the PNG to 390**. The screenshot was a crop, not an overflow, and nothing
in the image said which. It only became obvious when the probe reported
`vw=500` for a request of 390.

The fix was to stop trusting the window size and give the page a container of the
exact width — load it in a 390 px iframe and measure that frame's own
`documentElement`. Measured properly: `scrollWidth == clientWidth == 390`,
overflow 0.

**So: report the conditions the instrument actually applied, next to the result.**
A screenshot at a width the browser refused to honour looks exactly like a layout
bug. Same for a viewport, a timeout, a sample rate, a model version, a container
size — if you asked for X, print what you got before believing the output.

This is the fifth member of one family in this run, and the family is the point:
`--max-result` truncated while the header said nothing was dropped; a `\b`
redaction filter on macOS `sed` matched nothing and printed what it was hiding;
an em-dash sweep rewrote a tuple and clobbered a variable; an unpinned `ruff`
checked a different ruleset than CI; and now a viewport that was never 390.
**In each case the tool reported success while doing something other than what
was asked.**

## Committing in a shared worktree

**Use `git commit -- <paths>`. Never `git add` then `git commit`.**

`git add` writes to an index every session in this worktree shares, so *any*
window between staging and committing lets another session's commit sweep your
staged files into its own. Narrowing what you stage shrinks the blast radius; it
does not close the window, because the window is the mechanism.

`git commit -- <paths>` commits working-tree content for those paths in one
operation with no staging step. No window, no shared state.

**The one exception, because the rule cannot cover it.** `git commit -- <paths>`
only commits paths git already tracks; it cannot introduce a new file. A new file
needs `git add <path>` followed immediately by `git commit -- <path>`. That
reopens the window, so keep it to a single file and commit in the next command —
and if the lock is lost, re-check what landed rather than assuming.

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

**The sentence is the claim, not the JSON beside it.** On 2026-08-23 an alert
read *"trailing-24h cost is climbing 12.50 USD/h faster than usual, against a
window baseline of -15.33 USD/h"*. The evidence dict had `delta_per_h` correct
the whole time; only the prose was wrong. 12.50 was the *recent rate*, not the
excess — the change was +27.82/h, from falling at 15.33 to rising at 12.50 — so
the sentence attached "faster than usual" to the wrong quantity and understated
the move by more than half.

This is the worst version of the failure, because the number a human acts on is
the one in the sentence. State a rate, a baseline and a change as three separate
quantities rather than letting one number stand in for another, and pin the
wording with a test carrying real values.

## Time

All timestamps are timezone-aware. This machine is UTC+5 (Asia/Almaty) and the
work is graded across timezones, so every emitted timestamp carries an explicit
offset or a `Z`. Never emit a naive local time.

## Units

Never sum across pay models or currencies. USD balance, GBP balance, package
credits, trailing spend and postpaid credit are five different things; a single
"total spend" number mixing them would be fiction. Aggregate only within a unit.

## Verification before delivery

Four gates, not two. This section previously listed only the first two, which
meant a green result here did not mean the repository was green — the type
checker and the consistency check were the ones actually catching defects.
Every version is pinned for the same reason: an unpinned checker runs a
different ruleset locally than in CI, so the two can disagree and neither is
wrong.

```bash
uv run --with pytest pytest tests/ -q
uv run --with 'ruff==0.15.17' ruff check .
uv run --with pyright==1.1.411 --with pytest==8.3.4 --with httpx pyright
uv run tools/repo_checks.py consistency
```

`.claude/CLAUDE.md` carries the same list; if they ever diverge, that is a bug
in one of them.
