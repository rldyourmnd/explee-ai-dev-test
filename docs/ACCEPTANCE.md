# Final acceptance matrix

One row per required deliverable. Maintained by the orchestrator (`surface:3`).

**The rule that governs this file:** a row is never marked `DONE` because an agent
reported it done. It is marked `DONE` only when the verification command in its
row has been run and its output recorded here, against a named SHA on a clean
tree. The external review's central structural point is that it could not run
anything, so every machine-level claim in this repository reads to a grader as an
unverified assertion. This matrix exists so that our evidence survives that
standard — a reader who trusts nothing we say can re-run column 5 and check.

**Status vocabulary, deliberately narrow:**

- `DONE` — verification command run, output recorded, at the stated SHA.
- `EXISTS-UNVERIFIED` — the artifact is present but its claim is not yet proven
  by a command run on a clean tree. Not a passing state.
- `BLOCKED` — waiting on a decision only the human can make (see Part 4).
- `ABSENT` — not in the repository.

**A verification command must be satisfiable.** The first version of row X.3
checked `grep -c 'max-result 6000' docs/HANDOFF.md` → `0`, which can never pass:
the removal note itself quotes the old flag, so the word survives its own
deletion. It now greps only inside fenced `bash` blocks, testing the runnable
instruction rather than the prose. This is the same defect Task 3 found in the
`AGENTS.md` `HostName` gate, and it is easy to write twice — a gate that cannot
reach its passing state is worse than no gate, because it reads as rigour.

**Baseline SHA for this pass: `479187b`** (working tree carries only `.serena/`
tooling churn and the docs added in this pass). No row below is `DONE` yet, which
is the honest state, not a formatting placeholder.

## Task 1 — spend observability

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| 1.1 | Monitor source | `task1-spend-observability/monitor.py` | `surface:2` | EXISTS-UNVERIFIED | `git ls-files --error-unmatch task1-spend-observability/monitor.py && sha256sum $_` | — |
| 1.2 | Alert output | `task1-spend-observability/alerts.jsonl` | `surface:2` | **ABSENT** — exists on host (10 alerts, 7688 B, 18:03Z) but not in the repo | `wc -l task1-spend-observability/alerts.jsonl && python3 -c "import json,sys;[json.loads(l) for l in open(sys.argv[1])]" $_` | — |
| 1.3 | Public dashboard, no login | `https://spend.nddev.it.com/` | `surface:2` | **DNS VERIFIED, HTTPS NOT YET** — record resolves globally; end-to-end fetch still blocked by a local negative-cache entry, so this is **not** marked done | `curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' https://spend.nddev.it.com/` from outside the host, no `Host` override, no `--resolve`, no cookies; plus cert subject/issuer | — |
| 1.4 | ≥6 h observation proof | `docs/SNAPSHOT-22-14Z.md` (to be created) | `surface:3` | pending 22:14Z | see "Six-hour snapshot procedure" below | — |
| 1.5 | Task 1 trace | `task1-spend-observability/TRACE.md` | `surface:2` | **ABSENT** | `uv run tools/export_trace.py` without `--max-result`; then scan | — |
| 1.6 | Task 1 README | `task1-spend-observability/README.md` | `surface:2` | EXISTS-UNVERIFIED | `git ls-files --error-unmatch $_` | — |

## Task 2 — STT benchmark

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| 2.1 | Task directory | `task2-stt-benchmark/` | `surface:5` | **PRESENT** as of 18:54Z — `surface:5` active, writing metric tests | `test -d task2-stt-benchmark` | — |
| 2.2 | Brief | `docs/briefs/task2.md` | `surface:3` | present, committed this pass | `git ls-files --error-unmatch docs/briefs/task2.md` | — |
| 2.3 | Corpus manifest + frozen audio hash | TBD | `surface:5` | ABSENT | `sha256sum <audio>` recorded before any engine is run | — |
| 2.4 | Gold reference transcript | TBD | `surface:5` | ABSENT | two annotators + adjudication, policy pre-registered | — |
| 2.5 | Raw engine outputs (≥6 engines) | TBD | `surface:5` | ABSENT | hash each raw output before normalisation | — |
| 2.6 | Eval code + result table | TBD | `surface:5` | ABSENT | re-run eval, compare to published table | — |
| 2.7 | Published no-login report | *no URL yet* | `surface:5` | **BLOCKED** — decisions 4 and 5 | `curl` from external network, clean profile | — |
| 2.8 | Task 2 trace | TBD | `surface:5` | ABSENT | export without truncation, then scan | — |

## Task 3 — harness artifact

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| 3.1 | Harness artifact | `task3-harness-artifact/reviewer-protocol.md` | `surface:8` | **DONE** — verified independently by `surface:3` at 18:55Z, all three copies agree | `shasum -a 256 task3-harness-artifact/reviewer-protocol.md`; same on the installed plugin copy; and `gh api repos/nddev-it-com/rldyour-claudecode/contents/…?ref=33c9185 --jq .content \| base64 -d \| shasum -a 256` | `f4f1424b2f5b75a62e7e9864d5cfd3a4150d16aee6760d270911abbb2e816e04` |
| 3.2 | 2–3 line explanation | `task3-harness-artifact/README.md` | `surface:8` | EXISTS-UNVERIFIED | `git ls-files --error-unmatch $_` | — |
| 3.3 | Clean trace | `task3-harness-artifact/TRACE.md` | `surface:8` | **BLOCKED** — decision 2 | export without truncation, then scan | — |

## Cross-cutting

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| X.1 | Gates green on a **clean tree at the final SHA** | — | `surface:3` | pending final | see "Final gate procedure" below | — |
| X.2 | Lossless export (no truncation, fail-closed) | `tools/export_trace.py` | `surface:8` | open — `--list` fixed in `d7c2b24`; truncation/image/UTF-8/malformed paths still open | regression tests + `--max-result` rejected in submission mode | — |
| X.3 | `--max-result` removed from handoff instructions | `docs/HANDOFF.md` | `surface:3` | **DONE** — command run 18:46Z, output `0` | `awk '/^\`\`\`bash/{f=1;next} /^\`\`\`/{f=0} f' docs/HANDOFF.md \| grep -c -- '--max-result'` → **`0`** | at `479187b`+this pass |
| X.4 | Delivery route: history rewrite + publish | this repo | `surface:3` | **procedure written, NOT RUN** — runs once, after 22:14Z and after workers finish | see "Publication procedure" below | — |
| X.5 | Type check clean | `pyright` | `surface:8` | **18 errors at `8111af1`** — reported by CI, non-blocking until 0 | `uv run --with pyright --with pytest pyright` → `0 errors` | — |
| X.6 | CI attached to the final commit | `.github/workflows/ci.yml` | `surface:3` | added this pass; first run pending | GitHub Actions run, green pytest + ruff, on the final SHA | — |
| X.7 | Working tree free of third-party identifiers | whole repo | `surface:3` | **DONE** — command run 18:58Z, empty output | `git ls-files -z \| xargs -0 grep -lEi '<client-a>\|<client-b>'` → empty; `grep -lE '^[[:space:]]*HostName[[:space:]]+'` → empty; no public IPs | at this pass |
| X.8 | **History** free of third-party identifiers | all refs | `surface:3` | **OPEN** — working tree is clean, history is not | `git log -p --all \| grep -ci '<identifier>'` → `0`, after the rewrite | — |

## Six-hour snapshot procedure — runs at 22:14Z, collection must not stop

Written ahead of time so it is executed, not improvised at the deadline. The
sampler is **not** restarted, stopped, or reconfigured to take this snapshot.

```bash
ssh server-nddev-amsterdam '
  set -e
  D=/opt/explee-spend-monitor/data/raw_samples.jsonl
  S=/opt/explee-spend-monitor/snapshots
  systemctl is-active explee-raw-sampler          # BEFORE
  mkdir -p $S
  cp -a "$D" "$S/raw_samples.6h.jsonl"            # copy, never move
  sha256sum "$S/raw_samples.6h.jsonl"
  stat -c "%s bytes" "$S/raw_samples.6h.jsonl"
  wc -l < "$S/raw_samples.6h.jsonl"
  python3 - "$S/raw_samples.6h.jsonl" <<EOF
import json,sys,datetime
ts=[];bad=0
for ln in open(sys.argv[1]):
    ln=ln.strip()
    if not ln: continue
    try: ts.append(json.loads(ln)["ts"])
    except Exception: bad+=1
p=sorted(datetime.datetime.fromisoformat(t.replace("Z","+00:00")) for t in set(ts))
span=(p[-1]-p[0]).total_seconds()
gaps=[(b-a).total_seconds() for a,b in zip(p,p[1:])]
print("first",p[0].isoformat()); print("last",p[-1].isoformat())
print("span_s",int(span),">=21600:",span>=21600)
print("max_gap_s",max(gaps) if gaps else 0)
print("malformed",bad)
EOF
  systemctl is-active explee-raw-sampler          # AFTER
'
```

Every number that comes back is recorded in `docs/SNAPSHOT-22-14Z.md` and its
SHA-256 becomes the hash in row 1.4. Collection continues past the mark; longer
is better, and the snapshot is a copy, not a stopping point.

## DNS evidence for row 1.3, 19:05Z

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
