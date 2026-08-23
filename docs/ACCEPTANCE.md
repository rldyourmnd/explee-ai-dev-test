# Final acceptance matrix

**Derived line by line from [`docs/TASK.md`](TASK.md), which is the authority.**
Where any other document in this repository paraphrases the task, that document
is wrong and `TASK.md` is right. This matrix was re-derived from the verbatim
text at 19:38Z rather than from accumulated understanding, because paraphrase
drift is how a submission fails a requirement everyone was sure was met.

**The rule that governs this file:** a row is never `DONE` because an agent
reported it done. It is `DONE` only when its verification command has been run
and its output recorded. The external review could not run anything, so every
machine-level claim here reads to a grader as an unverified assertion; this
matrix exists so a reader who trusts nothing can re-run column 5.

**Status vocabulary:** `DONE` (command run, output recorded) · `EXISTS-UNVERIFIED`
(present but unproven — not a passing state) · `BLOCKED` (human decision) ·
`ABSENT`.

**A verification command must be satisfiable.** Row X.3's first version checked
`grep -c 'max-result 6000'` → `0`, which can never pass because the removal note
quotes the flag. The `AGENTS.md` `HostName` gate needed **three** revisions for
the same reason. A gate that cannot reach its passing state reads as rigour while
proving nothing, and both directions must be tested — against the leak *and*
against a clean file that merely mentions the pattern.

**Baseline: `d3963d6`**, re-derived 19:38Z. The previous baseline said `479187b`,
which `main` had long passed — a matrix that lags the tree is the same defect as
a stale board, and this is the artifact a grader is handed as proof.

## Requirements common to all three tasks

Verbatim: *"Export that conversation as a TRACE.md per task… It must be the REAL
conversation — exported or copy-pasted as-is, every message and every correction,
verbatim. A hand-made 'trace' tells us nothing."*

| # | Requirement | Owner | Status | Verification | Hash / SHA |
|---|---|---|---|---|---|
| A.1 | TRACE.md per task, real, verbatim, tool-exported | all | 1 of 3 present | tool header present; `grep -c 'not verbatim\|truncated'` → `0`; leak scans | — |
| A.2 | Every conclusion backed by data | all | ongoing | each claim carries its measurement | — |

## Task 1 — spend observability

Verbatim send list: *"the code (a file), your alerts.jsonl, a publicly deployed
dashboard link (opens without login), and TRACE.md."*

| # | Deliverable (task wording) | Path / URL | Owner | Status | Verification | Hash / SHA |
|---|---|---|---|---|---|---|
| 1.1 | **"the code (a file)"** — singular | `task1-spend-observability/monitor.py` | `surface:2` | **GAP** — we ship `monitor.py` *and* `raw_sampler.py`. Fix is self-sufficiency, not merging: `monitor.py` must poll the API directly so one file is the whole system. Merging would mean stopping the collector | run `monitor.py` alone against the live API, with no other file present | — |
| 1.2 | **"your alerts.jsonl"** | `task1-spend-observability/alerts.jsonl` | `surface:2` | **DONE** 19:15Z — 11 lines, 0 unparseable, **0 timezone-naive**, 0 future-dated, every row has `ts`/`text`/`provider` | parse every line; assert `ts` carries an offset; assert required keys | at `7aebe52`+ |
| 1.2a | Task text: *"Required keys: ts … and text. Recommended: provider"* | same | `surface:2` | **DONE** — all three present on all 11 rows | included above | — |
| 1.2b | 5 of 11 lines are `package_exhaustion` resends — must read as justified refiring, not spam | same | `surface:2` | **open** — line-by-line audit against raw records | each line traced to raw records around its `ts` | — |
| 1.3 | **"a publicly deployed dashboard link (opens without login)"** | `https://spend.nddev.it.com/` | `surface:2` | **DONE** — HTTP 200, 53461 bytes, valid Let's Encrypt cert for that exact hostname, `/healthz` 15/15 fresh; verified externally, no `Host` override, no `--resolve`, no auth | `curl` from outside the host + `openssl s_client` | — |
| 1.4 | **"Run your monitor for at least 6 hours"** | `docs/SNAPSHOT-22-14Z.md` | `surface:3` | pending **22:14Z** — the one unrecoverable deliverable | six-hour snapshot procedure below | — |
| 1.5 | **TRACE.md** | `task1-spend-observability/TRACE.md` | `surface:2` | **ABSENT** — export only when the session ends, never with `--max-result` | tool header; lossy/leak scans | — |
| 1.6 | *"a dashboard where one glance tells you what is happening"* | served at 1.3 | `surface:2` | EXISTS-UNVERIFIED | one-glance judgement, not mechanical | — |
| 1.7 | Unavailable rule has **never fired**; 900 s threshold sits above every observed outage | `POLICY-SENSITIVITY.md` | `surface:2` | **open** — sound reasoning, currently an assertion. Sensitivity table turns it into a defended policy | recompute the window at 5/10/15/20 min thresholds; report missed known outages | — |

## Task 2 — STT benchmark

Verbatim: *"a comparison of ≥5 STT engines of your choice on the same audio
(~1 hour), and the eval behind it"*; *"Send: a published comparison report (host
it anywhere, send the link) — **the report is the main artifact** — plus
TRACE.md."*

| # | Deliverable (task wording) | Path / URL | Owner | Status | Verification | Hash / SHA |
|---|---|---|---|---|---|---|
| 2.1 | Task directory | `task2-stt-benchmark/` | `surface:5` | PRESENT — harness, glossary, reference policy, frozen pre-registration | `test -d` | — |
| 2.2 | **"the same audio (~1 hour)"** | frozen corpus | `surface:5` | **DONE** — 120 hashed segments, exactly 3600.0 s, span rule declared *before* cutting | manifest + SHA-256 of publisher original | — |
| 2.3 | **"≥5 STT engines"** | — | `surface:5` | **ABSENT** — 6 planned so one failure cannot drop below 5 | count engines with raw output on disk | — |
| 2.4 | **"the eval behind it"** — design frozen before results | `PREREGISTRATION.md` | `surface:5` | **DONE** — `FROZEN` anchored to commit `9fd6ff8`, not a self-declared stamp | `git show 9fd6ff8` | `9fd6ff8` |
| 2.5 | Gold reference transcript | — | `surface:5` | **ABSENT — critical path**, two annotators + adjudication. Nothing can be scored without it | policy pre-registered; adjudication recorded | — |
| 2.6 | Raw engine outputs, hashed before normalisation | — | `surface:5` | ABSENT | hash each raw output | — |
| 2.7 | **"a published comparison report … host it anywhere, send the link"** | `https://stt.nddev.it.com/` | `surface:3` built the host, `surface:5` writes the report | **HOST LIVE, REPORT PENDING** — HTTP 200, 725 B, Let's Encrypt cert `CN=stt.nddev.it.com`, no auth, verified externally 19:45Z. Only the report content is outstanding | `curl -sSI https://stt.nddev.it.com/` + `openssl s_client` for cert subject/issuer | — |
| 2.8 | **TRACE.md** | — | `surface:5` | ABSENT | tool header; lossy/leak scans | — |
| 2.9 | Licence posture stated, `NC` named as the contestable leg | report | `surface:5` | **required** — not a footnote | report text | — |

## Task 3 — harness artifact

Verbatim: *"One file, plus 2-3 lines on where it lives and what it does."*
*"Send: the file."*

| # | Deliverable (task wording) | Path / URL | Owner | Status | Verification | Hash / SHA |
|---|---|---|---|---|---|---|
| 3.1 | **"One file"** | `task3-harness-artifact/flow-memory-sync.md` | `surface:8` | **DONE** — re-verified 19:37Z after the artifact *changed* from `reviewer-protocol.md`; submitted copy is byte-identical to the installed source | `shasum -a 256` on submitted and installed copies | `26d0ed17…f607a04` |
| 3.2 | **"plus 2-3 lines on where it lives and what it does"** | `task3-harness-artifact/README.md` | `surface:8` | **DONE** — states path, what dispatches it, what it does, and names its own tradeoff (two of seven steps call helper scripts, so it is not fully standalone) | read | — |
| 3.3 | **TRACE.md** | `task3-harness-artifact/TRACE.md` | `surface:8` | **DONE** — decision 2 closed by the human: *nothing is withheld*. Genuine fresh session 19:30:50Z→19:34:27Z, tool-exported, 2140 lines. Scans: 0 truncation markers, 0 foreign slugs, 0 public IPs, 0 credentials, 0 real `HostName` lines | header check + four scans | — |
| 3.4 | **"nothing more"** — package contains exactly the file, the lines, the trace | `task3-harness-artifact/` | `surface:3` | **DONE** — directory holds exactly those three. `PROVENANCE.md` and the quarantine record now live in `docs/` as internal | `ls task3-harness-artifact/` → 3 entries | — |

## DNS evidence for row 1.3, 18:59Z

Recorded because "the dashboard is up" is exactly the kind of agent assertion the
review refuses to accept, and because the local and global answers disagree.

| Check | Result |
|---|---|
| Authoritative (`ns23.domaincontrol.com`) | `188.166.77.47` |
| Google DoH (`dns.google/resolve`) | `Status 0`, `188.166.77.47` |
| Cloudflare DoH | `Status 0`, `188.166.77.47` |
| `curl https://spend.nddev.it.com/` from this machine | **fails**, `could not resolve host` |

The record exists and has propagated to two independent public resolvers. The
failure is local: this machine's stub resolver cached an `NXDOMAIN` from before
the record was created, and `curl` goes through `getaddrinfo` while `dig` queried
the resolver directly — which is why the two disagree.

**Row 1.3 stays open.** Propagation is not the deliverable; a real HTTPS response
from outside the deployment host is. Verification will not use `--resolve` or a
`Host` header, because that would prove the server works while bypassing the
exact thing under test. Waiting for the negative TTL is the honest path.

## Publication procedure — written now, **run exactly once, at the end**

Sequencing is the whole point. Three sessions are live in this working tree, and
`git filter-repo` plus a force-push under them destroys uncommitted work.
History also keeps growing, so rewriting now means rewriting twice. **Do not run
any of this until the 22:14Z snapshot is taken and every worker has finished and
committed.**

**Preconditions, all of them, checked in this order:**

1. 22:14Z snapshot complete, row 1.4 filled.
2. `surface:2`, `surface:5`, `surface:8` finished, committed, and confirmed idle.
3. `git status --porcelain` empty.
4. Every worker told that history is about to be rewritten and that they must not
   commit again — after the force-push, their local `main` is a different history
   and any commit made on the old one is stranded.
5. `gddy` authenticated by the human (OAuth is a browser flow; agents cannot do
   it) if the dashboard hostname route is chosen.

**Step 0 — rollback insurance, before touching anything.** `filter-repo` is not
undoable in place.

```bash
git bundle create ../explee-backup-$(date -u +%Y%m%dT%H%M%SZ).bundle --all
git rev-parse HEAD > ../explee-backup-head.txt
git for-each-ref > ../explee-backup-refs.txt
```

Rollback is then `git fetch ../explee-backup-*.bundle 'refs/*:refs/*'` into a
fresh clone, and a force-push of the recovered `main`. The bundle lives outside
the repository so the rewrite cannot eat it.

**Step 1 — remove the quarantined traces from all history.** Only 3 commits touch
them; every later commit still gets a new SHA.

```bash
git filter-repo --force \
  --invert-paths \
  --path TRACE-orchestration.md \
  --path task3-harness-artifact/TRACE-task3-quarantined.md
```

**Step 2 — scrub identifiers that live in *other* files' history.** The working
tree was sanitized in a normal commit, but the pre-sanitization blobs of
`docs/RUNLOG.md` and `docs/ORCHESTRATION.md` still contain them. Write
`../replacements.txt` outside the repo:

```
<client-a>==>REDACTED-CLIENT
<client-b>==>REDACTED-CLIENT
```

```bash
git filter-repo --force --replace-text ../replacements.txt
```

**Step 3 — verify across every ref, not just the tip.** This is the step that
decides whether publication is safe:

```bash
git log -p --all | grep -ci '<client-a>\|<client-b>'          # expect 0
git log -p --all | grep -cE '^\+[[:space:]]*HostName[[:space:]]+'  # expect 0
git log --all --diff-filter=A --name-only --format= | sort -u | grep -i trace
git rev-list --count HEAD
```

Publication proceeds **only** if the first two return `0`. If either is
non-zero, stop and re-scope the replacements — do not publish and clean later,
because a push cannot be recalled.

**Step 4 — re-point and force-push.** `filter-repo` deletes the `origin` remote
deliberately, so this is an explicit act rather than an accident:

```bash
git remote add origin git@github.com:rldyourmnd/explee-ai-dev-test.git
git push --force origin main
```

**Step 5 — make public, then re-verify from outside.** Flip visibility, then
confirm from a clean unauthenticated context that what is public is what was
intended — the scan above proves the local history, not what GitHub serves.

**Known consequences, stated rather than discovered later:**

- **Every SHA changes.** Any SHA recorded in this matrix before the rewrite is
  void afterwards. Final SHAs must be captured *after* Step 4, and CI (X.6) must
  be green on the rewritten commit, not the pre-rewrite one.
- A rewrite cannot retract what was already fetched. This repository has 0 forks
  and 0 stars, and has only ever been pushed to by this session, so the exposure
  window is the GitHub-side cache alone — which is why rewriting is viable here
  and would not be on a repository with real clones.
- Publication is decision 3 and remains the human's. This procedure is the
  *mechanism*; it does not make the choice.

## Gate integrity incident, 19:01Z — every "gates green" claim was unreproducible

The most serious self-inflicted finding of this run, recorded in full because it
invalidates earlier claims made by this session.

**What happened.** CI had been failing on **every pushed commit** —
`ca27622`, `4db6c5b`, `a0f8885`, `d895b12` — while this session reported "gates
green, ruff clean" each time. Both were telling the truth about different tools:

| Where | Command | Ruff | Result on the same tree |
|---|---|---|---|
| This machine | `ruff check .` | 0.15.17 | `All checks passed!` |
| CI | `uv run --with ruff ruff check .` | 0.16.4 | **49 errors** |

There was no `ruff.toml` and no pinned version, so `ruff check .` meant
"whatever ruff happens to be installed". The rule defaults moved between
releases, and the gate moved with them.

**Why it went unnoticed.** The local result was green, and green results do not
get investigated. CI was added at 18:52Z and its status was never read — the
evidence existed for twenty minutes before anyone looked at it. Adding CI and not
checking it is worse than not adding it, because it manufactures the appearance
of verification.

**Fix.** `ruff.toml` states the rule selection explicitly, so the gate no longer
depends on the version, and CI pins `ruff==0.15.17` as well. Verified across both
versions after the config landed:

```
uv run --with 'ruff==0.15.17' ruff check .   → All checks passed!
uv run --with 'ruff==0.16.4'  ruff check .   → All checks passed!
```

**Consequence for the matrix.** No row may cite a gate result produced by an
unpinned tool. The canonical command is now:

```bash
uv run --with pytest pytest tests/ -q
uv run --with 'ruff==0.15.17' ruff check .
```

**A second, smaller breach at the same moment.** The `d895b12` push ran the gates
and then pushed *unconditionally* — the `&&` chained the commit to the push, not
the gate result to either. A test was red at the time (Task 1's in-flight
pending/firing work, uncommitted) and the push proceeded anyway. The pushed
commit was docs-only so nothing broken was published, but the discipline failed
before the luck held. Pushes are now gated on both exit codes explicitly.

## Final gate procedure — clean tree only

The 18:04Z gate ran against a working tree holding an uncommitted Task 1 edit.
That was recorded at the time, and the external review picked it up: a green
result on a dirty tree does not prove the pushed commit. Final gates therefore
run only when `git status --porcelain` is empty, and the record includes the
commands, tool versions and exit codes:

```bash
git status --porcelain          # must be empty
git rev-parse HEAD              # the final SHA
uv --version; python3 -V; ruff --version
uv run --with pytest pytest tests/ -q; echo "pytest exit=$?"
ruff check .;                   echo "ruff exit=$?"
```
