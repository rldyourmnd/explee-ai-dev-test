# External review — snapshot `6efe631`, 2026-08-23T18:05:06Z

Produced by an independent review agent with authenticated read-only GitHub
access and public web access. It did **not** run code or tests, SSH anywhere,
inspect running services or DNS, or see any pane. Every machine-level claim in
this repository is therefore treated by it as an *agent assertion*, not proof —
that distinction is the spine of the review and worth internalising.

**Verdict: not submission-ready at this snapshot.**

Four of its code findings were independently re-checked against `main` before
this file was written, and all four reproduce:

| Finding | Confirmed at |
|---|---|
| Dispersion uses adjacent slopes, not all-pairs | `monitor.py:864` |
| Credits from different providers are summed | `monitor.py:1782`, contradicted by prose at `:2115` |
| `/alerts.jsonl` ignores `--alerts` | `:2213` reads the global, `:2298` parses the arg |
| Documented export truncates | `docs/HANDOFF.md:50` |

---

## Part 1 — Assessment

### Task 1 — spend observability

**What the repository proves.** `monitor.py`, `raw_sampler.py`, `README.md` are
present. Heterogeneous provider responses are normalised without assuming the
provider ID implies a shape. HTTP errors, unparseable responses and HTTP-200
schema misses are represented separately rather than silently becoming zero.
Timestamps are UTC with `Z`. Alert state is persistent. Alert output is one JSON
object per physical line. Top-ups and package resets are modelled as events, not
incidents. Alert conditions use sustain periods and material-change bands rather
than firing every cycle. Tests exist for transient errors, sustained outages,
flapping, top-ups, timezone-aware timestamps, restart behaviour and deterministic
replay — the repository proves the tests *exist*, not that they passed on the
submitted commit.

**Absent:** `alerts.jsonl`, `TRACE.md`.

**Unusually valuable history.** Three commits preserve a wrong inference and its
correction rather than presenting a false clean-room result:

- `79be7bd` — corrected a temporary balance increase and reversion misread as
  continuous spend.
- `347b115` — corrected the maths of a trailing-window spend report: the rate is
  now `value / window`, its derivative retained only as a trend.
- `6ce1e80` — replaced timer-based alert restatements with material-change bands
  after the live alert log showed minor drift hiding a real deterioration.

**Agent assertions this reviewer cannot prove:** collector active, 3,536 records,
no gaps > 45 s, no malformed lines, 1 h 50 m elapsed, monitor deployed, 114 tests
green and Ruff clean. The board itself notes the final gate ran against a working
tree carrying an uncommitted Task 1 edit, so even our own status board does not
claim that result proves `6ce1e80` in isolation.

**Missing against acceptance criteria:** a proven ≥6 h window; a public no-login
dashboard URL; the final `alerts.jsonl`; a clean `TRACE.md`.

#### Open correctness findings

1. **Provider-specific credits are aggregated as though fungible.** Grouping by
   `(pay_model, unit)` sums every `credits_package/credits` provider into one
   value and one burn rate. One provider's package cannot fund another, so the
   total has no operational interpretation despite every operand being called
   "credits". A grader inspecting the one-glance summary sees this immediately.
2. **The dashboard labels unsustained candidates as firing.** `snapshot()`
   evaluates rules and assigns every current candidate to `state.alerts`; the
   append path applies a *separate* sustain clock. A condition can therefore read
   as firing on the dashboard before it has met the incident threshold. The UI
   must distinguish pending-sustain, active-and-fired, and active-but-already-
   acknowledged-within-the-same-band.
3. **The anomaly-dispersion description does not match its implementation.**
   `Estimate.dispersion` is described as the MAD of "pairwise slopes" but
   computes slopes only between adjacent subsampled points — an adjacent-
   difference distribution, not the all-pairs distribution Theil–Sen uses. This
   alters anomaly sensitivity and makes the "6 MAD" claim imprecise. Either
   compute the stated distribution or rename and justify the actual statistic.
4. **The raw sampler is not literally verbatim.** It stores `r.text[:8000]` with
   no original length, truncation flag or content hash. Any response beyond
   8,000 characters is irrecoverably truncated — relevant precisely because the
   upstream API is allowed to return odd payloads. Harmless only if measured and
   stated.

### Task 2 — STT benchmark

Nothing exists in repository-visible form: no `task2-stt-benchmark/`, no brief,
no corpus manifest, no engine adapters, no reference transcript, no eval code, no
report, no public URL, no trace. **The largest recoverable threat to the
submission.**

### Task 3 — harness artifact

`reviewer-protocol.md` and `README.md` exist; the README gives the requested
short explanation. The artifact shows mature design: six independent reviewer
tracks, a structured finding schema, confidence thresholds, file-first report
transport, a compact parent summary, explicit correction and consolidation
behaviour. `f9ef23b` records the selection against alternatives and why they were
rejected.

**Not proven:** that this exact file is the current daily-use source, was copied
byte-for-byte from its claimed location, or has the claimed usage history. Needs
a source permalink, source and submitted SHA-256, and references showing the real
workflow invokes it.

**Missing:** a clean `TRACE.md`. The directory holds a quarantined trace instead.

#### Open artifact-quality findings

1. **"Read-only" is a prompt convention, not an enforced invariant.** The
   artifact grants every reviewer unrestricted Bash, acknowledges Bash is
   arbitrary, then relies on an instruction that Bash may write only to the
   report directory — and concludes project files are unreachable because Edit,
   Write and NotebookEdit are absent. That conclusion is false as a technical
   security property: Bash can modify, delete, rename or exfiltrate. Wildcard MCP
   allowlists may also expose write-capable actions. Either enforce report-path-
   only writes with a wrapper or sandbox, or describe it honestly as
   "source-preserving by contract".
2. **Cited GitHub issue dispositions are inaccurate.** The artifact says #16789,
   #20531 and #23463 were all closed as not planned. Actual: #16789
   `not_planned`, #20531 **`completed`**, #23463 `not_planned`; separately cited
   #26251 closed as **duplicate**, not as an unresolved generic limitation. Small
   to fix, but conspicuous in an artifact whose theme is evidence quality.

### Cross-cutting trace exporter

**`--list` defect: closed.** `list_sessions()` now scopes to one project,
defaults to the cwd project slug, and avoids enumerating others even in its error
path, with regression coverage for explicit selection, defaulting, unknown-project
failure, and keeping unrelated names out of stdout and stderr (`d7c2b24`).

**Verbatim-integrity defect: still open.** `docs/HANDOFF.md` instructs agents to
export with `--max-result 6000`. The exporter truncates long tool results while
the generated header claims nothing was dropped. A *disclosed* truncation is
still not verbatim. Further lossless gaps: image blocks replaced with an omission
marker; malformed JSONL silently skipped by `load()`; invalid UTF-8 replaced
rather than failing. For these traces the exporter should **fail closed** whenever
it cannot produce a lossless representation.

---

## Part 2 — Risk register

1. **Critical — the six-hour window is interrupted or the submission finalised
   early.** Unrecoverable. Closure: immutable copy at or after 22:14Z; first and
   last timestamps spanning ≥21,600 s; max consecutive gap reported; malformed
   count reported; line count, byte size and SHA-256 recorded; collector active
   before and after; no restart merely to take the snapshot.
2. **Critical — Task 2 entirely absent.** Closure: public report, corpus
   manifest, gold transcript policy, raw engine outputs, eval code, result table,
   statistical analysis, clean trace.
3. **Critical — mandatory traces conflict with confidentiality and verbatim
   integrity.** Closure: no `--max-result`; export fails on malformed records or
   unsupported blocks; session JSONL SHA-256 recorded; trace scanned for
   credentials, unrelated project identifiers, hostnames, IPs, private URLs and
   third-party names; clean package excludes quarantined files and contaminated
   history.
4. **High — required public artifacts not externally reachable.** Closure: HTTPS
   200 from an external network, no cookies/auth/VPN/`Host` header/local DNS
   override, clean browser profile, matching certificate hostname, timestamped
   external verification.
5. **High — unsafe delivery route.** Making the current repository public would
   expose material intentionally withheld; keeping it private and sending only
   its URL may make it inaccessible. Closure: a clean allowlisted package or
   fresh submission repository with no contaminated history.
6. **High — non-actionable aggregate credit totals.** Closure: no total across
   provider-specific credits; risk ranking by provider-level time-to-impact; a
   regression test that fails if two credit providers are combined.
7. **High — alert output may be too noisy or too quiet.** `6ce1e80` is real
   progress. Residual: the 900 s unavailability threshold sits deliberately above
   every observed self-healing outage — a policy choice, not a measured truth;
   the dashboard calls unsustained candidates firing; the final `alerts.jsonl` is
   absent so timestamps and top-up behaviour cannot be checked; unit tests
   prevent direct top-up alerts but a wrong top-up segment cut can still distort
   burn, runway and anomaly rules; that work is uncommitted; the anomaly
   threshold's claimed distribution is not what is computed. Closure: every final
   line audited against raw records around its timestamp; no alert caused solely
   by a top-up, reset or reverted blip; a sensitivity table across sustain and
   unavailability thresholds; pending and fired separated in the UI; every
   timestamp parsed as timezone-aware.
8. **Medium — the claimed raw source of truth may be truncated.** Closure:
   maximum original body length measured; if nothing reached the cap, say so;
   future records carry original byte length, truncation flag and full-body hash.
   **Do not restart the collector before the six-hour mark to deploy this.**
9. **Medium — deliverable claims not reproducible from the submitted state.** The
   raw capture is gitignored, no CI result is attached to the final SHA, and the
   latest gate ran against an uncommitted edit. Closure: clean working tree,
   exact final SHA, gate commands with tool versions and exit codes, and an
   evidence bundle sufficient to recompute headline claims.

---

## Part 3 — Work plan by pane

### `surface:3` — orchestrator

1. **Preserve the collector above every other objective.** No restart, replace,
   reconfigure or move before the six-hour point. Record each heartbeat with
   service state, first timestamp, last timestamp, line count, malformed count
   and maximum consecutive gap.
2. **At the six-hour point, snapshot immutably without stopping collection.**
   Copy the raw log, compute SHA-256, record bytes and lines, compute the exact
   first-to-last span. Keep collecting afterwards.
3. **Create a final acceptance matrix** — one row per required deliverable: path
   or public URL, owner, status, verification command, final SHA/hash. Never mark
   an item complete because an agent says it exists.
4. **Repair the trace process before Task 1 or Task 2 export.** Remove
   `--max-result 6000` from `docs/HANDOFF.md`; make the exporter reject requested
   truncation in hiring-test mode; fail on malformed JSONL and unsupported image
   blocks; record the raw session SHA.
5. **Convert human decisions into written briefs immediately.** Create
   `docs/briefs/task2.md` with the approved audio source and spend ceiling;
   record the Task 3 trace and delivery decisions.
6. **Do not make the current repository public.** Build the chosen delivery route
   with an allowlist, not a denylist: exclude quarantined traces, `.git`, raw
   session logs unless approved, machine metadata, internal orchestration
   material and unrelated identifiers. Produce a package inventory, SHA-256
   manifest and an independent contamination scan.
7. **Run final gates only on the exact clean final tree.** Record
   `git status --porcelain`, `git rev-parse HEAD`, test/Ruff/type-check commands,
   exit codes and tool versions.

### `surface:2` — Task 1

1. **Do not touch the raw sampler process.** Check collector state before and
   after any deployment; only restart or replace the derived monitor.
2. **Remove the aggregate `credits_package/credits` card.** Keep provider
   credit values and burn rates separate; rank by time-to-impact or projected
   package exhaustion. Add a regression test with two credit providers asserting
   no summed total is produced.
3. **Finish and commit the top-up segment-cut work, then replay from T0.** Test
   genuine top-ups, package resets, reverted blips, top-up-plus-same-interval-
   spend ambiguity, large one-off charges and events near the minimum projection
   span.
4. **Separate pending candidates from fired incidents in the dashboard.** A
   candidate inside its sustain interval displays as pending, not firing;
   historical fired lines and currently active conditions must be
   distinguishable. Cover pending, newly fired, same-band active, deteriorated
   and recovered in tests.
5. **Make the anomaly statistic match its documentation.** Either compute the MAD
   over the intended all-pairs slope sample, or rename it adjacent-slope MAD and
   recalibrate the threshold against the observed window. Add synthetic outlier
   tests, observed-event replay and documented threshold sensitivity.
6. **Audit every final `alerts.jsonl` line against raw evidence** — preceding and
   following raw interval, rule inputs, sustain duration, materiality band, and
   whether a top-up/reset/blip occurred nearby. Zero unexplained lines, zero
   top-up-only incidents.
7. **Run a policy sensitivity report.** Recompute the window for unavailability
   thresholds of 5, 10, 15 and 20 minutes, multiple runway thresholds and the
   selected materiality bands. Report line count, unique incidents,
   duplicate/restatement count and missed known outages.
8. **Make `/alerts.jsonl` serve the path selected by `--alerts`.** Bind the
   resolved CLI path to the handler instead of a module global. Integration test
   with a non-default path.
9. **Measure the 8,000-character raw-body cap.** Maximum observed body size and
   count of records at exactly 8,000. Do not deploy a sampler change that
   interrupts the current window.
10. **After six hours, commit the final artifacts** — `alerts.jsonl`, coverage
    evidence, a complete untruncated `TRACE.md` — and verify the public dashboard
    from outside the deployment environment.

### `surface:5` — Task 2

1. **Create `docs/briefs/task2.md`** as soon as the human supplies audio
   authorisation and spend ceiling: provenance, privacy constraints, deadline,
   engine budget, publication restrictions, exact definition of done.
2. **Freeze one authorised ~1 h corpus before inspecting any engine result.**
   Preserve the original file, SHA-256, duration, channel layout, sample rate,
   speaker count and a segment manifest. Natural Russian speech with dense
   English IT terminology; synthetic audio may supplement but must not be the
   main corpus.
3. **Build the gold reference before ranking engines.** Two independent
   annotators plus adjudication. Pre-register rules for Latin vs Cyrillic
   technical terms, product-name spelling, numerals and abbreviations, filler
   words and false starts, punctuation, unintelligible spans, speaker labels, and
   English inflections inside Russian grammar.
4. **Run at least six engines** so one failure does not drop the benchmark below
   five. Defensible slate: OpenAI GPT Transcribe, Deepgram Nova-3 multilingual,
   Google Chirp 3, ElevenLabs Scribe v2, Azure Speech, Speechmatics. OpenAI
   exposes multilingual and keyword hints; Deepgram explicitly supports
   Russian/English code-switching; ElevenLabs exposes smart multilingual
   transcription and keyterm prompting; the rest provide Russian baselines and
   terminology controls that must be measured, not assumed.
5. **Keep the comparison fair.** Identical source audio, segmentation,
   resampling, channel handling and retry policy. Store raw output before
   normalisation. Never compare one engine with a glossary against another's
   default. Publish separate default-model and terminology-assisted rankings.
6. **Use metrics designed for this speech, not WER alone:** normalised overall
   WER; CER; WER on code-switched spans; exact IT-term precision, recall and F1;
   product/vendor name recall; Latin-to-Cyrillic substitution rate; hallucination
   rate; omission rate; code-switch boundary error rate; speaker attribution and
   timestamp quality; cost, latency, retries and failed requests.
7. **Compute uncertainty on paired segments.** Paired bootstrap confidence
   intervals; report when the data does not establish a statistically meaningful
   winner. Include per-category error tables and representative examples, not
   only a composite score.
8. **Publish a reproducible no-login report** — model identifiers and dates,
   exact parameters, preprocessing, reference policy, raw-output hashes, cost,
   limitations, privacy treatment, and a decision rule tied to meeting use.
   Export a complete real trace without result truncation.

### `surface:8` — Task 3 and trace tooling

1. **Treat the project-scoped `--list` defect as closed; fix the remaining
   lossless-export defects.** Remove hiring-test use of `--max-result`; fail on
   malformed records, invalid UTF-8 replacement or image omission; add regression
   tests; run the type checker alongside pytest and Ruff.
2. **Execute the human's Task 3 trace decision without reconstructing the old
   conversation.** No hand-editing, no synthesis. A new run must be a genuine
   session and must state, without exposing identifiers, that an earlier trace was
   withheld for confidentiality.
3. **Correct the artifact's read-only claim.** Prefer a path-validating
   report-writer tool with no arbitrary Bash; or an isolated disposable worktree
   or filesystem sandbox; or OS-level read-only source mounts plus a writable
   report directory; or post-run source-tree hash and `git diff --exit-code`
   verification. If none is implemented, rename the property "source-preserving
   by reviewer contract".
4. **Correct issue metadata and pin the check date** for #16789, #20531, #23463
   and #26251.
5. **Prove source identity and real use:** source repository permalink, source
   commit SHA, SHA-256 of source and submitted file, byte-for-byte comparison
   result, and references from the active review workflow showing it is invoked.
6. **Deliver only the permitted Task 3 package** — artifact, 2–3 explanatory
   lines, and the clean trace the human selects. Quarantine records stay internal.

---

## Part 4 — Decisions only the human can make

**1. Public dashboard hostname.** Add the record at the authoritative DNS
provider (minimal change; needs account access, and credentials must never enter
a trace); use another controlled domain (fast, changes the hostname); redeploy to
a platform-generated HTTPS hostname (no external DNS needed, adds migration and
fresh verification risk); or submit without one (fails a stated deliverable).

**2. Task 3 trace.** A new genuine clean session (real trace, but not the
original contaminated attempt — omission must be disclosed); ship traceless
(protects confidentiality, conflicts with the global requirement); publish the
quarantined original (exposes third-party information); hand-edit or redact
(violates verbatim and undermines evidentiary value). No option preserves both
the entire original attempt and confidentiality — the human chooses which
constraint governs.

**3. Repository visibility and delivery.** Keep private and submit a clean
archive plus public Task 1/2 URLs; create a fresh public submission repository
with allowlisted files and orphan history; grant the grader private access
(friction, still exposes quarantined material); make the current repository
public (publishes quarantined files and history); rewrite history then publish
(complex, and rewriting cannot retract caches or prior clones).

**4. Task 2 audio source.** Authorised real company-style meeting (most
representative; needs explicit authorisation); authorised meeting from the
candidate's own work (fast and realistic; different speakers); public Russian
technical discussion (clear publication rights; less representative acoustics and
interruptions); scripted or synthetic (easy ground truth, weak evidence for
natural code-switching — supplement only).

**5. Task 2 budget and account set.** Maximum total spend; which vendors may
receive the audio; whether account creation requiring payment details is allowed;
whether glossary-assisted runs are in scope; whether zero-retention or regional
processing is required. The agent implements the approved set rather than
silently substituting free-tier availability for experimental design.

**6. Submission timing.** Before 22:14Z fails the six-hour requirement; after it
preserves eligibility and allows evidence finalisation; continuing beyond six
hours improves event coverage but should not delay a hard external deadline
without an explicit decision.

**7. Operational alert policy.** Runway warning and critical horizons; the
15-minute unavailability threshold; the postpaid credit floor; materiality bands;
whether recovery notifications are required. Data can show the consequences of
each choice; it cannot invent the company's response SLA.

---

## Part 5 — What the grader will notice first

**Most likely to earn credit.** (1) The raw observation source was prioritised
before dashboard development — the correct response to an API with no history
endpoint, and keeping derived state replayable is strong judgement. (2) The
commit history shows genuine measurement-driven correction rather than claimed
rigour: a withdrawn rate-limit inference, a corrected reverted-balance blip,
corrected trailing-window maths, and timer-based restatements replaced after
observing real alert output. (3) Alert lifecycle and reviewer-output transport
show operational maturity — sustain periods, persistent state, material-change
refiring, event-versus-incident separation, replayability, file-first reports.

**Most likely to lose credit.** (1) Task 2 is absent — not a quality defect but a
missing task and missing main artifact; now the largest critical-path workload.
(2) Direct deliverables missing or unreachable: six-hour proof incomplete, no
public URL, no `alerts.jsonl`, no Task 1 trace, no Task 2 report or trace, no
clean Task 3 trace. Only the continuity of the observation window is
unrecoverable. (3) Trace/privacy contradictions and visible semantic overclaims:
a "verbatim" invocation that truncates, a "read-only" artifact permitting
arbitrary Bash, incorrect external issue dispositions, a company-level total of
non-fungible credits, and machine claims not tied to a clean final commit.

## Ruthless priority order

1. Do not interrupt the collector.
2. Make the human-only decisions immediately — especially Task 2 audio/budget and
   submission timing.
3. Start Task 2 and freeze its evaluation design before inspecting outputs.
4. Repair trace export integrity before producing Task 1 or Task 2 traces.
5. Resolve public access for Task 1 and the eventual Task 2 report.
6. Fix non-fungible-credit aggregation, pending-versus-fired UI semantics, and
   anomaly-statistic naming.
7. Produce final artifacts from a clean exact SHA and deliver through a clean
   package, not the current repository history.
