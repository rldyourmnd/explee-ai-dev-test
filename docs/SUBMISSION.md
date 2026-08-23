# Submission package

The form is now known, and it changes the plan. Read this before doing any more
delivery work.

## The form

| Field | Type | Notes |
|---|---|---|
| Name | text | Danil Silantyev |
| Where did we talk | text | `@Danil_Silantyev` |
| **Task 1 — Alert log** | **file, required** | `alerts.jsonl`, every line needs a `ts` with a timezone |
| Task 1 — Code | file | *one file (zip it if several)* |
| Task 1 — Dashboard link | url | deployed, opens without login |
| Task 1 — Agent trace | file | `TRACE.md` |
| Task 2 — Report link | url | published comparison |
| Task 2 — Agent trace | file | `TRACE.md` |
| Task 3 — The artifact | file | one file |
| Notes | textarea | *"Doubts, what you'd cut, what you're proud of"* |

Partial submission is explicitly allowed.

## What this cancels

**The repository is never submitted.** Not as a link, not as an archive. Seven
files and two URLs go to the employer, and nothing else. Therefore:

- **P3 delivery work is cancelled.** No fresh public submission repository, no
  allowlisted package, no orphan history, no `filter-repo` rewrite, no all-refs
  identifier scan, no force-push, no post-rewrite CI run. The quarantined traces
  in Git history never reach the employer because the history never reaches the
  employer. The working repository stays private and stays as it is.
- **Repository visibility stops being a decision.** It remains private.
- The contamination risk that has shaped a dozen decisions now applies to exactly
  one surface: the **contents of the files we upload**. Scanning shifts entirely
  to the seven artifacts.

This removes hours of work and the single largest irreversible-action risk in the
project. It does not remove the rule-3 discipline: the two `TRACE.md` files are
uploaded, so they must still be clean by construction.

**"Code — one file (zip it if several)"** also settles the argument we had about
architecture. The employer permits an archive. `monitor.py` is already
self-sufficient, so submit it alone as the code file; mention `raw_sampler.py` in
the Notes as the bootstrap collector that protected the observation window, or
zip both. Either is compliant. Nothing about the running system needs changing
for this.

## Assemble here

Build `submission/` in the repository root, containing exactly what gets
uploaded, with the filenames a stranger can identify:

```
submission/
├── task1-alerts.jsonl          from the clean post-T1 window
├── task1-monitor.py            self-sufficient single file
├── task1-TRACE.md              exported, submission mode
├── task2-TRACE.md              exported, submission mode
├── task3-flow-memory-sync.md   byte-identical to its upstream source
├── LINKS.md                    the two URLs, so nothing is retyped from memory
└── NOTES.md                    draft of the Notes field
```

Nothing else. No READMEs, no provenance files, no acceptance matrix, no
orchestration board. Those exist for us and for the audit trail; the employer
asked for seven things.

## Pre-flight, run against `submission/` and nothing else

```bash
# every line parses and carries a timezone-aware ts
python3 - <<'PY'
import json, sys
bad = 0
for i, line in enumerate(open('submission/task1-alerts.jsonl'), 1):
    if not line.strip(): continue
    d = json.loads(line)
    ts = d.get('ts', '')
    if not (ts.endswith('Z') or '+' in ts[10:] or '-' in ts[10:]):
        print(f'line {i}: naive ts {ts!r}'); bad += 1
    if 'text' not in d:
        print(f'line {i}: missing text'); bad += 1
print('FAIL' if bad else 'OK: every line parses, every ts carries an offset')
PY

# leak scan across every uploaded file
grep -rnoE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' submission/ | sort -u
grep -rnE 'HostName[[:space:]]+[^[:space:]]' submission/
grep -rniE 'unrelated-client-a|unrelated-client-b' submission/
```

Expect: no naive timestamps, no third-party project names, no real `HostName`
config lines, and no IP addresses other than ones we deliberately publish.

Then verify both URLs from a clean browser profile with no login, no cookies and
no local DNS override, and record the status codes.

## The Notes field

The form asks for *doubts, what you'd cut, what you're proud of*. That is an
invitation, and it is the one place to surface what a grader would otherwise have
to dig for. Draft it last, keep it short, and cover:

- **Proud of:** the collector started before the monitor existed, because the API
  has no history endpoint and the window could not be rebuilt; and the retraction
  chain, especially withdrawing our own recommended STT configuration after
  finding its score came from 19 collapsed transcripts.
- **Doubts, stated as numbers not adjectives:** the publisher transcript is
  edited, so absolute WER is inflated for every engine and we infer the magnitude
  rather than measure it; one hour resolves only large differences; the tuned
  track covers Whisper only; the coverage guardrail was amended after outputs
  existed and is labelled as such.
- **What we would cut:** name it honestly rather than pretending everything
  earned its place.
- **Where the evidence lives that the form has no field for:** `ALERT-AUDIT.md`
  replays the window, checks every evidence field, runs top-up counterfactuals
  and publishes a failing result. Mention it exists and what it found.

## Timing

Assemble only when the workers are done: after the clean-window `alerts.jsonl`
with a passing audit, and after both traces are exported at genuine session end.
Assembling early means shipping an artifact that stopped before the work did.
