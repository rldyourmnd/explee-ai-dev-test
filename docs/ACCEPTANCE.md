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
| 1.3 | Public dashboard, no login | *no URL yet* | `surface:2` | **BLOCKED** — decision 1 | `curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' <URL>` from an external network, clean profile, no `Host` override | — |
| 1.4 | ≥6 h observation proof | `docs/SNAPSHOT-22-14Z.md` (to be created) | `surface:3` | pending 22:14Z | see "Six-hour snapshot procedure" below | — |
| 1.5 | Task 1 trace | `task1-spend-observability/TRACE.md` | `surface:2` | **ABSENT** | `uv run tools/export_trace.py` without `--max-result`; then scan | — |
| 1.6 | Task 1 README | `task1-spend-observability/README.md` | `surface:2` | EXISTS-UNVERIFIED | `git ls-files --error-unmatch $_` | — |

## Task 2 — STT benchmark

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| 2.1 | Task directory | `task2-stt-benchmark/` | `surface:5` | **ABSENT** | `test -d task2-stt-benchmark` | — |
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
| 3.1 | Harness artifact | `task3-harness-artifact/reviewer-protocol.md` | `surface:8` | EXISTS-UNVERIFIED | `sha256sum` of source *and* submitted file, plus `diff` — identity is claimed, not yet proven | — |
| 3.2 | 2–3 line explanation | `task3-harness-artifact/README.md` | `surface:8` | EXISTS-UNVERIFIED | `git ls-files --error-unmatch $_` | — |
| 3.3 | Clean trace | `task3-harness-artifact/TRACE.md` | `surface:8` | **BLOCKED** — decision 2 | export without truncation, then scan | — |

## Cross-cutting

| # | Deliverable | Path / URL | Owner | Status | Verification command | Final SHA / hash |
|---|---|---|---|---|---|---|
| X.1 | Gates green on a **clean tree at the final SHA** | — | `surface:3` | pending final | see "Final gate procedure" below | — |
| X.2 | Lossless export (no truncation, fail-closed) | `tools/export_trace.py` | `surface:8` | open — `--list` fixed in `d7c2b24`; truncation/image/UTF-8/malformed paths still open | regression tests + `--max-result` rejected in submission mode | — |
| X.3 | `--max-result` removed from handoff instructions | `docs/HANDOFF.md` | `surface:3` | **DONE** — command run 18:46Z, output `0` | `awk '/^\`\`\`bash/{f=1;next} /^\`\`\`/{f=0} f' docs/HANDOFF.md \| grep -c -- '--max-result'` → **`0`** | at `479187b`+this pass |
| X.4 | Delivery package, allowlisted | TBD | `surface:3` | **BLOCKED** — decision 3 | package inventory + SHA-256 manifest + independent contamination scan | — |

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
