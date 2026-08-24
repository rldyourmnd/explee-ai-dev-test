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
   the new process resuming from an offset that should not exist. That mistake
   replayed 16 records where a full window was intended. And never detect
   "replay finished" by grepping the log for the serve banner: the previous
   run's banner is still there. Count `[replay]` lines before starting and wait
   for the count to rise. `tools/deploy_monitor.sh` encodes both.

   **The post-deploy check now fails loudly when it cannot run.** It previously
   could not: every `ssh` call lacked `-n`, so the remote command consumed the
   script's own stdin when piped and the collector-after assertion was never
   reached. The container shipped and nothing proved the sampler survived it.
   An `EXIT` trap now assumes verification absent until the final line, so any
   exit before it prints what was not proved and returns non-zero, and it
   distinguishes `ABORTED BEFORE DEPLOY` from `DEPLOYED BUT NOT VERIFIED`. A
   post-check that can silently not-run is a comment, not a safety check.

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
   matches `HostName` followed by whitespace, so the Task 3 trace scored 2 on a
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
   being run: it flagged its own instructions. `HostName\s+\S+` has the same
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

   **One exception exists and it is not hand-editing: `--excise`.** Two shipped
   traces use it, so this rule would otherwise read as a guarantee the tooling
   no longer gives. A contaminated tool result, output from an enumerating call
   that named unrelated work, can be removed by `--excise <turn|tool_use_id>`,
   which is a different act from redaction in four ways the tool enforces:

   - it is **addressed by a named unit**, a turn number or tool-call id, never
     by a content pattern, so it cannot take more than intended;
   - it removes the **whole tool result**, never the matching lines inside it:
     stripping 4 names from a 52-line listing leaves 48 lines of an enumeration
     that should not have been run, and invites the question of what they held;
   - the marker left behind is **generated by the exporter**, naming what
     produced the result, why it went, and how many lines went with it, so a
     reader never has to trust that the excision is what it claims;
   - the header stops claiming a plain verbatim export and states **"verbatim
     except for N documented excisions"**, N mechanically derived, on the first
     screen.

   Messages, reasoning, corrections and failed attempts are never touched, and
   excision cannot reach a tool *input*, so it cannot launder a session's own
   prose or commands. It is permitted under `--submission`; every other override
   is refused there. Auditing a count: anchor to the generated line prefix,
   `grep -cE '^> \*\*\[EXPORTER\] Tool result removed\.\*\*'`. A substring
   search also counts the trace quoting the marker in conversation, and single-line
   removals read "1 line removed", singular.

5. **Two traces were quarantined and are now deleted from the working tree.**
   `TRACE-orchestration.md` was produced before rule 3 existed and carried an SSH
   config dump and nine unrelated client IPs; the Task 3 trace carried a
   directory listing naming an unrelated client project. Both were first
   quarantined in place, then removed entirely at 18:52Z on the way to
   publication. **They still exist in git history**, which is why publication
   requires the history rewrite in `docs/ACCEPTANCE.md` and not merely a
   `git rm`. A deleted file and a purged file are different things, and only the
   second is safe to publish.

## Scan by SOURCE, not by content: you cannot regex a name you have never seen

The foreign-slug guard matches project slugs shaped `-Users-<user>-Developer-…`.
A session listing prints **bare names**, so the guard had nothing to match, and a
real client identifier reached a submission artifact through a check that passed
honestly.

**Content matching is structurally incapable of closing this class.** It can only
find identifiers someone already thought to write down. The next leak will be a
name nobody has seen.

The fix is to match on **provenance**: flag any tool result produced by an
*enumerating call* (`ListAgents`, `export_trace --list`, `modal app list`,
`docker ps`, `gh repo list`, reading an SSH config) and require that result to be
reviewed, or absent, before an export can pass. **The exporter knows what command
produced each block, which is knowledge no regex over the output can recover.**

### And knowing the rule is not applying it

The same session that leaked this had, minutes earlier, written *"I cannot
identify surface:3 without enumerating"* and chosen a safer route, **after
already having enumerated twice.** Later it deliberately avoided `modal app list`
for exactly this reason and wrote that rule into this file. It authored the rule
it had already broken, in the same session, and did not notice.

It also wrote *"a scan licenses a conclusion only about the pattern it matches"*
into the very commit that shipped the contaminated trace.

**So a rule in this file is not a safeguard.** Only a check that runs is. Where a
rule matters, give it a gate; where it cannot have one, expect it to be broken by
someone who can quote it.

## Enumeration hazards: never list what you did not come to see

**Five** separate leaks in this run had one shape: **a tool's listing command
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
4. A listing of the session directory under `~/.claude/projects` named other
   projects on this machine, the same reach as (1), arrived at by hand rather
   than through the tool's flag, which is why fixing the flag did not close it.
5. `ListAgents` (the cmux session listing) returned ~30 rows spanning the whole
   machine while a worker looked for one pane. Four rows carried a real client
   name, and they contaminated the Task 2 trace. Caught only because the exporter
   had by then learned to flag results **by the call that produced them**; the
   content scanner saw nothing, because a session listing prints bare names and
   there is no pattern to write for a name nobody has seen yet.

Five for five. Assume the pattern is general, because it is: these commands are
*designed* to show everything you own, and a hiring-test trace is published
verbatim to strangers.

**What the tooling now enforces, so this section is not the only line.**
`tools/export_trace.py` fails the export closed on (a) any project slug other
than the one being exported, and (b) any tool result produced by a call it
recognises as enumerating, `ListAgents`, `docker ps`, `modal app list`,
`gh repo list`, an ssh-config read, `--list --project` pointed elsewhere, or a
listing of a home projects directory. The second check is the one that matters,
because it does not depend on recognising the leaked name. Instance 5 is the
proof: content matching had nothing to match, and provenance caught it anyway.
The recognised-enumerator list is a list of known commands, **not a proof of
completeness**: the sixth instance will be a command none of us has run.

**Measured breadth of the tools on this machine**, run as counts only, never
printing names, so this document and the trace that produced it stay clean:

| Command | Reaches |
|---|---|
| `gh repo list` | 36 repositories |
| `systemctl list-units` | 69 services on the droplet |
| `doctl compute droplet list` | 8 droplets |
| `docker ps` | 8 containers |
| `modal app list` | the whole workspace |
| `gddy domain list` | the whole registrar account |

**Standing check, not a reminder.** This class has now bitten five times, listed
above, and the `gh`/`doctl`/`gddy` listings measured here are the same gun
unfired. **Before a worker uses a tool that is new to this repository,
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

## Coordinating panes: delivery is a claim, not an action

`cmux send` **types** text into a target pane's prompt. It does not submit it.
The text sits there, unsent, until something presses Enter, and a silent
non-delivery is indistinguishable from a delivered message unless you look.

**Use `tools/cmux_send.sh surface:N 'your message'`. Do not hand-roll the
sequence below.** The script types the text, *waits for the paste to finish
arriving*, presses Enter, waits for the redraw, reads the screen back, retries up
to four times, and exits non-zero if the text is still sitting at the prompt.

The wait is the whole point, and it is why the manual form kept failing: an Enter
sent immediately after `send` **races the paste**, landing while the text is
still arriving, so nothing submits and the sender never finds out. A human was
pressing Enter by hand to unstick panes before the script existed.

The three steps it automates, for when you need to understand what it is doing:

```bash
cmux send --surface surface:N 'your message'
cmux send-key --surface surface:N Enter
cmux read-screen --surface surface:N --lines 8      # not optional
```

Reading the screen back is how you learn whether it landed. If your text is
still sitting at the prompt, it did not send: press Enter again. If the screen
shows `Press up to edit queued messages`, the recipient is mid-task and your
message is queued, which is fine and needs nothing.

This has already cost real wall-clock here: on 2026-08-23 two panes sat idle with
instructions unsubmitted in their buffers while the critical path waited.

**Two traps.** Never type into a pane showing an interactive menu or a selection
list: a keystroke can pick an option and wreck its state; press Escape first.
And never send fresh text into a buffer that already holds unsent text: `send`
appends, so you would submit a splice of two messages neither author wrote.
Press Enter on what is there instead.

The framing this repository uses everywhere else applies to messaging too:
**an unverified send is an assumption, and an assumption is not evidence.**

## A text sweep over source is a code change

On 2026-08-23 an em-dash sweep (a presentation change) rewrote a `&mdash;`
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

## Looking at the output beats grepping it: three times in one run

Three defects reached a live page having passed every textual gate, and every one
was obvious to a person who simply looked:

1. **A 390 px screenshot that was a 500 px crop.** It looked exactly like a
   layout overflow. Nothing in the image said which.
2. **A `--accent` bar rendering near-black** because the variable was never
   defined. The screenshot showed the *correct* colour, since the photographed
   card carried `.warn`, which sets that property by a different rule.
3. **`"3.0x typical decline , recorded as an event"`**, an em-dash sweep left a
   comma with the dash's leading space. `ruff`, `pyright`, 297 tests and the
   consistency check all passed it. A reader sees it instantly.

The pattern: **textual gates read the source; a reader reads the render.** Between
those two is a gap no amount of grepping closes, and it is where formatting,
CSS-computed values and generated prose live.

So a change that alters what a human sees needs a human-shaped check: open the
page. And note the inversion in case 2: the screenshot *was* the check, and it
passed while confirming a different rule than the broken one, which is why "look
at it" is necessary but not sufficient. Ask what the picture would have shown had
the thing been broken.

## Fix the generator, not its output

`snapshots/03` carries two em dashes while `01` and `02` carry none, because the
written files were stripped and the **template that produces them was not**, so every
future snapshot reintroduced the defect. Fixed in `b890efd`: the two lines in
`tools/snapshot_window.py` that write the snapshot markdown no longer emit them,
which is why `04` is clean. `03` still carries its two: an already-written
artifact is a separate cleanup, and it belongs to whoever owns that directory.

Cleaning output that a generator will regenerate is not a fix; it is a delay. When
a defect appears in generated content, the fix belongs in the generator, and the
existing artifacts are a separate cleanup.

## No logs means the platform refused to start, so stop reading the file

`security.yml` and `scorecard.yml` failed for hours, and **as of 2026-08-24 they
still do**. The signature: instant failure, **zero jobs created, no logs at
all**, and the run named by its file path instead of its `name:` field. Nothing
in either file is known to be wrong.

The leading theory was that `NDDev-it-com/ci-workflows`, whose reusable
workflows they call, had been **archived**, since GitHub will not serve a
reusable workflow from an archived repository. The owner un-archived it,
verified `archived=false`, and both workflows failed again identically on the
next push: zero jobs, no logs, named by path. **So that theory is unconfirmed
too** - either it was not the cause, or not the only one, or workflow
resolution is cached longer than one push, which is untested. This paragraph
says so rather than closing the case, because a fix that was applied and did not
work is evidence, and recording it as resolved would cost the next person the
whole hunt again.

**The cause of a CI failure can sit entirely outside your repository**, and this
signature says so. A job that runs and fails writes logs. A run with no logs
never started, which means the platform rejected it before executing anything,
which means the answer is in the platform's view of the world and not in the
YAML. Time spent re-reading the file is time spent looking where the answer
cannot be.

Four hypotheses have been tested and none has held, which is the useful part:

1. **Permissions delegation**: that `permissions: {}` at workflow level left a
   job-level `id-token: write` nothing to narrow from. Disproved by a
   counterexample already in this repository, `dependency-review.yml`, which
   does empty-then-elevate against the same pin and parses fine.
2. **Privileged scopes being rejected before job creation.** Disproved without
   spending a push, from run history: `scorecard.yml` requests `id-token: write`
   and **succeeded** at 2026-08-23T23:59:15Z. A theory that forbids a run which
   demonstrably happened is finished.
3. **Unresolvable pins.** The pins examined were `actions/checkout` and
   `astral-sh/setup-uv`, from other repositories entirely, so they could not
   explain a failure in calls to a third.
4. **The callee being archived.** Un-archiving it did not fix the runs. The
   most plausible remaining reading is that this was necessary but not
   sufficient, which is not the same as being the cause.

What settled it was **a re-run, not a file read**: the same run id, same commit,
same event went `success` to `startup_failure` with zero repository changes
between attempts. Holding every input fixed and watching the output flip proves
the variable is external. No amount of inspecting the file could have found
that, because the file was never the variable.

The counterexample lesson also has a trap in it, and it caught me: I first used
`dependency-review.yml` to argue cross-owner calls were fine. That file has
**never run** - it is `pull_request`-triggered and there had been no PRs - so its
registered `name:` proved GitHub could *parse* it, not that GitHub could
*execute* the call. Parsing and executing are different things, and only the
second touches the archived repository. **A component that has never executed
cannot testify about run-time behaviour.**

## A check can pass while testing something next to the break

The families above are about tools reporting success while doing something else.
This one is worse, because nothing misbehaved.

On 2026-08-23 the dashboard used `var(--accent)` for the lead card's left rule
and **`--accent` was never defined**. CSS does not fail loudly: an undefined
custom property makes the declaration invalid at computed-value time, so
`border-left-color` fell back to `currentColor` and rendered a near-black bar -
which is also the untinted-neutral result the spec exists to prevent.

Everything passed, honestly:

| Gate | Result | Why it could not see it |
|---|---|---|
| `ruff` | clean | it does not read strings as CSS |
| `pyright` | 0 errors | the stylesheet is a string literal |
| 295 tests | passed | none looked inside the stylesheet |
| **screenshots** | **showed the correct colour** | see below |

The screenshots are the instructive row. The leading group carried `.warn` at the
time, and `.card.lead.warn` sets `border-left-color` explicitly, so the broken
declaration was overridden in exactly the case that was photographed. **The visual
check confirmed a rule other than the one under test.** It was right, and useless.

So: when a check passes, ask what it would have looked like had the thing been
broken. If the answer is "the same", the check is not evidence. Both guards added
here were validated by **reintroducing the bug and confirming they fail**, rather
than trusting that they would.

One of them encodes a judgement rather than a fact: the lead card must use
`--accent` and never a status colour, because brick red has to keep meaning *act
now*. That is worth a test precisely because it is a decision that would
otherwise erode.

## `git checkout -- <file>` restores HEAD, not your last edit

Undoing a test mutation with `git checkout -- monitor.py` also destroyed an
uncommitted fix in the same file. The command was correct; the mental model was
not. Undo-my-experiment and restore-to-HEAD are the same operation **only when
nothing else in that file is uncommitted.**

Durable form: **commit first, then mutate, then restore.** A mutation test should
always run against a clean tree. It was caught one command later only because
someone grepped for the fix instead of assuming it survived.

## A documented command that succeeds and does nothing

`tools/policy_sensitivity.py` writes its document to **stdout**. The documented
regenerate command was `uv run tools/policy_sensitivity.py`, with no redirect. It
was run exactly as documented, redirected to a log so the run could be watched -
and after **45 minutes** every regenerated table sat in a log file while
`POLICY-SENSITIVITY.md` kept its three-hour-old numbers. Exit code 0. The command
succeeded and did nothing that was wanted.

**A documented command must be the whole command.** If the output only lands
because of a redirect, the redirect is part of the instruction, not a detail the
reader is expected to supply.

## A document that argues with itself

The same file had grown an *"Update, 21:14Z"* block acknowledging that the prose
above it was stale. **That is worse than being stale.** A stale document is
wrong; a document containing its own correction proves someone noticed and
patched around it rather than fixing it, and leaves the reader to work out which
half to believe.

Four claims in it were checkable and simply wrong once the window doubled:
16 outages became 29, across 10 of 15 providers rather than 13 of 15; *"none
beyond 10.5 minutes"* became a 15.5-minute outage; *"roughly eight lines an
hour"* became 3.9; *"the single line at k=6"* became three. The update block is
gone and the prose is current.

## The instrument can be your own reasoning

On 2026-08-23 a `burn_anomaly` on `meta_ads` reported a baseline of **-14.15
USD/h**. The argument against it was clean: a 24-hour trailing total inside a
5.8-hour window cannot have shed anything yet, so its derivative cannot be
negative. Confident, and wrong.

**The trailing window is the vendor's, not ours.** It held a full day of history
at T0 and has been shedding it ever since. The 30-day figure settled it in one
line: it fell 1,818 USD in six hours, and money cannot be un-spent. So -14.15
USD/h is a correct measurement of current spend running below the rate of a day
earlier.

Two things to keep. **A confident derivation from an unchecked premise is still
an unchecked premise**, four lines of arithmetic against the raw series
disproved it, and none of that arithmetic was hard, only unattempted. And the
real limitation surfaced only because someone looked: a rise in that derivative
can mean current spend rose *or* spend leaving the window fell, and a six-hour
window cannot separate them, because `r(t-24h)` predates T0. The alert may say
the trailing total turned upward; it may not say anyone spent faster.

Same family as the viewport that was never 390, except the instrument was the
reasoning rather than the tool.

## A gate that writes is not safe to run as a check

`tools/alert_audit_doc.py` verifies the alert log **and rewrites
`ALERT-AUDIT.md`** as it goes. Running it to "check the gate" therefore mutates a
tracked file, and in a worktree four sessions share, running it while another
session is mid-edit puts a foreign write into their working copy.

Separate the two jobs: a **verifier** exits non-zero and touches nothing; a
**generator** writes. If one command must do both, it needs a `--check` mode that
suppresses the write, and a third party checking someone else's gate should use
only that mode.

## `cmd | tail` reports tail's exit code, not the command's

```bash
uv run tools/alert_audit_doc.py 2>&1 | tail -1; echo "exit=$?"   # prints 0. Always.
```

`$?` after a pipeline is the **last** command's status. The audit was failing with
exit 1 and this reported success, twice, on a gate whose entire purpose is its
exit code.

Capture the status of the command itself:

```bash
uv run tools/alert_audit_doc.py > /tmp/out 2>&1; rc=$?; tail -1 /tmp/out; echo "exit=$rc"
```

Same family as everything else here: the pipeline succeeded, and the thing it
reported was not the thing under test.

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
exact width, load it in a 390 px iframe and measure that frame's own
`documentElement`. Measured properly: `scrollWidth == clientWidth == 390`,
overflow 0.

**So: report the conditions the instrument actually applied, next to the result.**
A screenshot at a width the browser refused to honour looks exactly like a layout
bug. Same for a viewport, a timeout, a sample rate, a model version, a container
size, if you asked for X, print what you got before believing the output.

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
reopens the window, so keep it to a single file and commit in the next command -
and if the lock is lost, re-check what landed rather than assuming.

This bit three times on 2026-08-23: `7a90b2f` carried Task 1's monitor fixes
under *"Record Task 2 publication"*, `1282ad1` carried Task 1's polling-loop
tests under *"Task 2: power simulation"*, and one orchestrator change landed
under an unrelated exporter subject. Nothing was ever lost, what was lost is
**discoverability**, a rationale filed under a subject line nobody searching for
it will read. A correct commit with the wrong message is a defect in the history,
which is one of the artifacts being graded here.

## Evidence

Every claim in a deliverable is a hypothesis plus the data behind it. "The API
is flaky" is not a finding; "429 on `tremendous` and `findymail` in the same
poll cycle at 16:01Z, 2 of 15 providers" is. If something cannot be measured,
say so explicitly instead of estimating quietly, the top-up/spend ambiguity in
`README.md` is the worked example.

**The sentence is the claim, not the JSON beside it.** On 2026-08-23 an alert
read *"trailing-24h cost is climbing 12.50 USD/h faster than usual, against a
window baseline of -15.33 USD/h"*. The evidence dict had `delta_per_h` correct
the whole time; only the prose was wrong. 12.50 was the *recent rate*, not the
excess (the change was +27.82/h, from falling at 15.33 to rising at 12.50) so
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
meant a green result here did not mean the repository was green, the type
checker and the consistency check were the ones actually catching defects.
Every version is pinned for the same reason: an unpinned checker runs a
different ruleset locally than in CI, so the two can disagree and neither is
wrong.

```bash
uv run --with pytest==8.3.4 pytest tests/ -q
uv run --with 'ruff==0.15.17' ruff check .
uv run --with pyright==1.1.411 --with pytest==8.3.4 --with httpx pyright
uv run tools/repo_checks.py consistency
```

`.claude/CLAUDE.md` carries the same list; if they ever diverge, that is a bug
in one of them.
