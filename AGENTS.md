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
   grep -cE '^[[:space:]]*HostName[[:space:]]+' TRACE.md   # must be 0
   ```

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
uv run --with pytest pytest tests/ -q && ruff check .
```
