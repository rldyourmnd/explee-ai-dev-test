# Commit map: pre-rewrite -> published history

The history was rewritten on 2026-08-24 to remove two quarantined traces and to
replace third-party identifiers in four paths. The rewrite **preserved every
commit** - it was not flattened, because the retraction chain is the evidence.

Rewriting changes every SHA. Documents and traces written before that date cite
the old SHAs, and those SHAs do not resolve in the published repository. Those
citations were **not edited**: a trace is a verbatim record of a session, and
changing a SHA inside one to look correct in hindsight is the precise
falsification this repository exists to argue against. The mapping is published
here instead, so every old reference stays navigable while every record stays
as it was written.

193 rewritten commits, in history order. 0 removed entirely.

This is the size of the **mapping**, not of the repository. It is fixed: the map
covers exactly the commits that existed when the rewrite ran, and commits made
after it have always had their published SHA and need no entry. A reader
comparing this to `git rev-list --count HEAD` should expect a larger number
there.

| pre-rewrite | published | subject |
|---|---|---|
| `0005510` | `df6b636` | Correct two stale claims in my own quarantine record |
| `01ed275` | `6aad3d2` | Record the polling-loop tests, and fix the index race properly |
| `0530326` | `3564cf2` | Snapshot the six-hour window, and the 12 seconds that were missing |
| `05c0839` | `2b26688` | Record why the deployment target's address is published, not scrubbed |
| `07a247c` | `70b6150` | Task 2: Qwen3-ASR adapter — IN PROGRESS, blocked upstream |
| `083ac13` | `f6b8109` | Keep the orchestrator's AGENTS.md sections, and correct one now-stale line |
| `0886087` | `cd37bc3` | Rule on the Task 2 corpus, including the leg of the licence that is weak |
| `0c500d5` | `49db8e0` | Commit the round-2 external review prompt |
| `0cde580` | `3e3838f` | Heartbeat 19:15Z — rows 1.2 and X.2 verified; tree clean before round-2 review |
| `0f2f4f4` | `c7d585c` | docs(monitor): two docstrings still described a cooldown the code removed |
| `1131c2d` | `9b4dc4f` | fix(checks): point the snapshot check at the artifact the tool actually writes |
| `1282ad1` | `cab3a7e` | Task 2: power simulation, 98% coverage policy, and an honest reading of the null |
| `14489e2` | `4b570c8` | Record the concurrency check against the live deployment |
| `17ad43e` | `477f895` | docs(acceptance): cross-page UI convergence passes LIVE for the first time |
| `1a40629` | `0b92a4f` | Add documented excision and scan tool results by source |
| `1baadf5` | `2daac7b` | Add the window snapshot tool, and rehearse it before it matters |
| `1bde1e7` | `2135cda` | Document what the captured window measured, not what was assumed |
| `1d30167` | `f4f2535` | Track tools/cmux_send.sh, which was mandated but not in the repository |
| `1d445be` | `548c21d` | Task 2: publish the ranking — Whisper large-v3-turbo, on the frozen rule |
| `1ee633e` | `e138758` | Refuse to export a trace naming another project |
| `1f5b350` | `fc1d7e0` | Fix three defects confirmed by external review |
| `1f62ad4` | `3b551d9` | Task 2: export TRACE.md with four documented excisions |
| `2094b88` | `1b6eea8` | Snapshot the finished state, and stop pinning a count that keeps moving |
| `21b9f68` | `111c29d` | Task 2: correct the recommendation after finding a defect in my own tuned run |
| `221c28c` | `645079e` | Pin the lint gate so local and CI check the same thing |
| `2486a60` | `a46c63c` | docs(acceptance): the guard refused its own author, and the pyright debt is cleared |
| `250989d` | `47bc6c9` | Task 2: distractor test changes the recommendation to large-v3 + glossary |
| `26a3bda` | `d6192f6` | Stop the anomaly line misstating its own headline number |
| `2eeaefc` | `a74759d` | Quarantine the Task 3 trace after a rule-3 leak |
| `30dbffa` | `bae8ae2` | Task 2: commit the evidence inventory so the numbers can be checked (P1.7) |
| `310299c` | `008a1b6` | Narrow the enumeration guard: four false positives blocked a real trace |
| `3398f0a` | `72b789d` | feat(submission): assemble the package as a script, 5 of 7 artifacts placed |
| `3475455` | `2da500b` | Verify the 8000-character raw-body cap independently |
| `347b115` | `36522ff` | Report trailing-window cost as a rate, not as its derivative |
| `34c93eb` | `e010abe` | Record the undefined CSS variable and the checkout that ate the fix |
| `35df417` | `294d394` | Measure what each threshold costs, and correct claims the data outgrew |
| `360c7f4` | `0943237` | Record the Task 1 reasoning that landed under a Task 2 commit message |
| `3629ab4` | `6458130` | Point the README at the audit, the snapshot, and what is deployed |
| `3647dbd` | `01afe61` | Keep Task 2 audio and full transcripts out of the repository |
| `383594d` | `bdf6697` | Compute each provider's discontinuities once per evaluation |
| `392d200` | `71797a4` | docs(task1): refresh the alert audit against the current raw window |
| `39c8a0e` | `4195a68` | Pre-review sync: refresh the board, record the verified dashboard, decide two blockers |
| `3a118cd` | `733a24c` | Make healthz directly testable and stop clipping alert evidence |
| `3b25f5b` | `dc420f8` | Task 2: declare the reference protocol and the residual-bias slice before drafting |
| `3de3880` | `f90900a` | docs(agents): a text sweep over source is a code change |
| `3e36357` | `f708ec8` | report: move the power analysis next to the ranking it qualifies (P2) |
| `3f11822` | `9e78346` | State the Task 3 trace disposition as it actually is |
| `409ec66` | `50faa55` | Stop a flickering condition re-announcing itself; audit every alert line |
| `410e9c1` | `193ca45` | Heartbeat 20:13Z — four hours captured, engines still short of five |
| `41e407d` | `e26e500` | Task 2: paired moving-block bootstrap and Holm correction — a real defect fixed |
| `430b472` | `ad9a980` | Fix the artifact's enforcement overclaim upstream and re-verify provenance |
| `43f7090` | `e2d457c` | Refresh the acceptance matrix against the measured tree, and state the gaps first |
| `44df6c3` | `03e386f` | Track the snapshot series, the T1 clean window, and cost discipline |
| `4561e45` | `c58b899` | Strip the two em dashes snapshot 03 inherited from the old template |
| `479187b` | `f33fdcc` | Heartbeat 18:40Z — stall unchanged; alerts.jsonl exists on the host, not in the repo |
| `4a0f93e` | `364c1ec` | docs(runlog): record the fourth gate I had not been running |
| `4ac8d73` | `5a4006a` | Bring the heartbeat log up to date |
| `4d696e8` | `23b3e7a` | docs(acceptance): the pyright exclusion is not freezing debt, it is growing it |
| `4db6c5b` | `d53bdab` | Record the publication track and the commit-attribution incident |
| `5326be4` | `55ec876` | Task 2: export TRACE.md via --submission, no overrides used |
| `533fb18` | `b6f6c95` | docs(agents): check that the instrument honoured the conditions you asked for |
| `544b79c` | `ebbe52f` | fix(submission): ship the live alert record, and place the Task 1 trace |
| `552c199` | `25e4c78` | docs(delivery): rewrite the history, keep it — the retraction chain is the evidence |
| `5553aec` | `f669b09` | Retract the drift claim: the audit was reading past its own data |
| `57788ad` | `88ed676` | Remove four claims my own code and commits disprove |
| `57fcf8c` | `8afcfbe` | Adopt the expanded orchestrator mandate |
| `5b2a3c2` | `17fa039` | Task 2: five engines ranked against an independent publisher reference |
| `5d07243` | `d5046dd` | Define --accent, which the lead card had been using without it existing |
| `5ea9fd6` | `29349ec` | docs(policy): regenerate the sensitivity tables on the full window |
| `5edd952` | `fd976f5` | test(task2): coverage from raw files, which scored blocks cannot detect |
| `601647b` | `ad6d1d0` | docs(agents): record the operational rules Task 1 learned the hard way |
| `613ff88` | `c54410b` | docs(agents): the instrument can be your own reasoning |
| `616c504` | `a8df940` | ci: adopt the Public OSS security suite from the GDS ci-workflows library |
| `61a307d` | `ad3f76c` | docs(reviews): state the round-2 gap instead of leaving a hole in the chain |
| `62d0996` | `3495947` | Correct my own audit prose: two lines fail, not one |
| `63148c9` | `fc5ca1d` | Make the dashboard's colour and hierarchy carry meaning |
| `6424ba0` | `c0c119e` | docs(agents): scan by source, not content — you cannot regex a name you never saw |
| `64dfe9d` | `01cdf3a` | report: make the three outputs three visibly separate things |
| `6540c7d` | `a5a1a1b` | Task 2: slice analysis — Parakeet is the trap the benchmark was built to catch |
| `66f018d` | `6b5c8f3` | State which six hours, since two clocks start at different times |
| `68a717a` | `b3b56cc` | Heartbeat 18:16Z — tunnel surfaced as a DNS alternative, flagged not taken |
| `6afb8f4` | `1edc2e1` | Task 2: log the slate extension as an amendment, before running either engine |
| `6b86adf` | `e781d98` | Commit the verbatim task, re-derive the matrix from it, record the send+Enter rule |
| `6c365f1` | `7bd02e0` | Heartbeat 17:52Z — correct the README status table after Task 1's retraction |
| `6c48282` | `8e91687` | Heartbeat 17:14Z — rule-3 leak in the Task 3 trace, Task 1 blocked on DNS |
| `6ce1e80` | `9c5f673` | Write alert lines on material change, not on cooldown expiry |
| `6e67d25` | `c8ec10b` | Record the first green CI runs |
| `6efe631` | `f61f2bc` | Heartbeat 18:04Z — steady, no new blockers |
| `73e1d17` | `2703bf5` | docs(board): make the top authoritative and label the rest a dated log |
| `778af57` | `eeeca64` | Task 2: amend the corpus to a talk with a publisher human transcript |
| `77e620a` | `8f68d4e` | fix(snapshot): 02 closes the six-hour minimum, not 01 — and my check looked in the wrong directory |
| `78e5d2c` | `55a5c81` | docs(readme): three false claims a grader reads first, and surface the best evidence |
| `7964031` | `8514d39` | Regenerate alerts and the audit from the deployed build, and generate the audit document instead of writing it |
| `79be7bd` | `0fd489c` | Stop reading a reverted balance blip as phantom spend |
| `79e86ec` | `a64190b` | Assert that a clipped body fails closed rather than yielding a wrong value |
| `7a90b2f` | `cd933c3` | Record Task 2's publication, and that it is three engines not five |
| `7a990f4` | `e14c697` | Record the four settled human decisions |
| `7aebe52` | `8167435` | Task 2: freeze the corpus — 120 hashed segments, exactly 3600.0 s |
| `7bebf40` | `f13b6c8` | Make deploy_monitor.sh fail loudly when its safety checks do not run |
| `80f6d75` | `70a7049` | Task 2: fix the test that asserted the corpus-shrinking behaviour |
| `8111af1` | `0889246` | Commit the external review and take the orchestrator's Part 3 items |
| `833e708` | `13e9da9` | Close the last directive-3 gaps: same-interval ambiguity and late cuts |
| `84fa057` | `4b41eeb` | docs(acceptance): live and replay diverged, so we ship what was emitted |
| `88f925c` | `02db262` | Export the session trace, verbatim except for 13 named excisions |
| `8bda88c` | `917da77` | Distinguish a pending condition from one that has actually been raised |
| `8cf0de0` | `125d48c` | Correct my own pyright claim, and state the deployment gap in the artifact |
| `8d742af` | `d617527` | docs(acceptance): reopen the top-up blocker and rule on it |
| `8df4d72` | `9f354c3` | Derive spend state from the raw log: adapters, robust burn, alert rules |
| `90b184b` | `05cf7cd` | Tighten the Task 3 README to the literal "2-3 lines" |
| `9108243` | `b9d686a` | docs(task1): snapshot the T1 window, resync alerts, correct two stale claims |
| `91fcc17` | `c7767a0` | docs: commit the documentation pass, to be run after the work stops |
| `9249e9e` | `a71b744` | Pre-flight the trace export so the six-hour mark is mechanical |
| `95cc83a` | `ccf2d62` | Refresh the stale Task 2 board section, and generalise the enumeration hazard |
| `97cec9f` | `1208dd8` | Harden trace exporter and quarantine the orchestration trace |
| `995cdb8` | `3566af2` | README: stop saying Task 3 withholds its trace |
| `9a85e34` | `15c34fc` | Name the short snapshot for what it is, and stop the tool repeating it |
| `9bb774e` | `d4c4730` | Task 2: declare the corpus span rule before cutting; full-precision local engines |
| `9c11385` | `ebb382f` | Heartbeat 17:25Z — Task 3 trace quarantined, exporter defect is cross-cutting |
| `9d97db8` | `e9dc0ec` | docs: the paragraph showcasing our honesty had itself gone false |
| `9dc3389` | `58848ab` | Task 2: report status to the orchestrator; its board is three hours stale |
| `9f11eaf` | `fddf239` | docs(briefs): track the final external review prompt |
| `9fd6ff8` | `73d9993` | Task 2: freeze the STT evaluation design before any engine output |
| `a0f8885` | `20edaa4` | Heartbeat 18:54Z — stall over, row 3.1 verified, max gap now recorded |
| `a134998` | `a65e8aa` | Task 2: cap Modal fan-out at 4 GPUs, fix the CI type errors |
| `a3c0008` | `8d218ef` | docs: contradiction sweep — the README was publishing the wrong corpus |
| `a648ac4` | `f97f063` | Heartbeat 18:28Z — all three workers idle, every open item needs the owner |
| `a7dfa14` | `ef23c56` | Re-export the trace: it was carrying client names a sanitised file no longer contains |
| `a942072` | `0a91129` | Stamp the alert audit with the data it audits, not the repository HEAD |
| `a9a01cd` | `ecc59e1` | feat(submission): place the Task 2 trace — verified, four documented excisions |
| `ac0e7c8` | `630d333` | report(ui): prose keeps its measure, data gets the screen |
| `ae0c474` | `df52b47` | Add orchestration status board |
| `ae2c7cb` | `86ddbec` | Record the gate run, the push, and the repository-visibility tradeoff |
| `aef0a1b` | `f35facd` | fix(licence): exclude the amended corpus transcripts, which the old rules missed |
| `af59628` | `265d510` | Record the meta_ads investigation, which refuted my own objection |
| `afa71e0` | `742a513` | docs(agents): a gate that writes is not safe to run, and a pipeline hides exit codes |
| `b28c388` | `a1e767a` | fix(checks): the future-timestamp gate could not see the format we actually use |
| `b4f51df` | `ea6ecf9` | Make monitor.py the whole system, so the deliverable really is one file |
| `b7b4165` | `9f63f2f` | Track the sensitivity generator and give the report provenance |
| `b80bb55` | `cb2b805` | feat(dashboard): adopt the shared warm-paper palette, and remove every em dash |
| `b890efd` | `c6bea3a` | Fix the em-dash generator in tools/, and pin pytest where AGENTS.md names it |
| `b8fe3d7` | `aa430fa` | Publish the dashboard, verify it externally, commit alerts.jsonl |
| `b94036a` | `05ca951` | docs(acceptance): the recommendation changed, and the reason is the best catch yet |
| `bc6b89f` | `71893f4` | Heartbeat 17:02Z — collector gap-free, Task 3 artifact written |
| `be519e8` | `1893179` | fix(tools): make the alert audit document deterministic |
| `bf7baac` | `824d80e` | docs(acceptance): row 2.10 met, and surface the evidence a reader would miss |
| `c012d54` | `c5a7743` | Document the one line where the repo's sampler differs from the running one |
| `c0dfefe` | `0708637` | docs(agents): a check can pass while testing something next to the break |
| `c10d3b5` | `9c0c86c` | Adopt git commit -- <paths>, and track the recommendation requirement |
| `c11f6cf` | `49645c1` | docs(delivery): P3 is cancelled — the repository is never submitted |
| `c26d47f` | `9fd0084` | Remove two space-commas the em-dash sweep left in rendered prose |
| `c37d6d0` | `5e08ae5` | docs(acceptance): rule the shared --warn value, and correct a verification claim |
| `c7d2ed2` | `83d9bc3` | docs(gates): make AGENTS.md list all four gates, and pin pyright |
| `c7e9e45` | `2b57358` | Task 2: fix four confirmed defects in the scoring and reference code |
| `c8c08e3` | `e6f3f25` | fix(submission): withhold the Task 2 trace — a real client name, four times |
| `c9ca7ff` | `c3dcc2e` | docs(task1): re-measure the 429 claim, which no longer holds absolutely |
| `ca27622` | `0a4cfe9` | Fail closed on any lossy export path |
| `cb036a9` | `45864c7` | docs(ui): track the shared UI spec both pages are being held to |
| `cc513d4` | `7b118a0` | docs(agents): looking beats grepping, and fix the generator not its output |
| `ce6fe1c` | `bee4d2e` | Heartbeat 19:29Z — two panes were idle on unsent input, not on a decision |
| `d020288` | `2de1442` | Record that the sentence is the claim, not the JSON beside it |
| `d0757d5` | `53507b9` | Script the monitor deploy, encoding the two mistakes I already made |
| `d0bd3cd` | `edc8de3` | Make the dashboard readable below the fold, and stop claiming the two paths cannot disagree |
| `d2b9b86` | `ae983f4` | Build for numbered snapshots and a clean T1 window |
| `d3963d6` | `fe27341` | Task 2: build the gold-reference pipeline and annotation workstation |
| `d71041b` | `bd59121` | Let the alert evidence line survive a 390px viewport |
| `d7c2b24` | `4a4d1a7` | Scope --list to one project and fix the unsatisfiable HostName gate |
| `d895b12` | `dbfd392` | Contradiction sweep: fix five claims that outlived their facts |
| `d9375b1` | `6074b30` | Sync alerts.jsonl to what the deployment has actually produced |
| `dbca310` | `9ecebae` | Task 2: correct the pre-registration dating, adopt meetily's engine config |
| `dc0125d` | `11f0e01` | Heartbeat 17:40Z — exporter risk closed at the source, repo synced |
| `dc120b9` | `6506889` | Record replay-determinism verification and two more defect fixes |
| `e1cb8b9` | `75c0c96` | fix(submission): my own scanner's false positive, and pin pytest in CLAUDE.md |
| `e355604` | `4f0f861` | Record the 390px check, and the measurement that lied |
| `e3da56a` | `352c677` | Audit every alert line against raw evidence; stop state reading the future |
| `e6d2a0f` | `568ee06` | Make the contradiction classes mechanically impossible |
| `e7af3a4` | `11fac9e` | Set up repository, trace exporter, and live spend capture |
| `ec624c6` | `d6a15c2` | Task 2: publish the report — and say plainly why it names no winner |
| `f086fe9` | `052be8c` | Register repository against the GDS estate standard |
| `f21487f` | `43e0cf1` | Close the fail-closed holes and separate the two override classes |
| `f44b221` | `b83aadc` | Verify row 1.1: one file really is the whole system |
| `f461895` | `94fe958` | Task 2: P1 methodological honesty, and the retraction made visible |
| `f541927` | `f93a936` | docs(acceptance): retract the divergence claim, and re-derive the ruling it justified |
| `f6acf74` | `78b8736` | docs(briefs): track the round-3 review prompt as edited |
| `f721684` | `877db42` | Record the Task 3 verification log as real command output |
| `f7d945e` | `1a6c6f1` | docs(agents): record the Modal GPU cap that caused a workspace outage |
| `f891b93` | `5b216f6` | docs(acceptance): record the two Task 2 results that argue against their author |
| `f91d4ef` | `2d663c1` | docs(acceptance): verify alerts.jsonl against the served endpoint, not the repo copy |
| `f9ad4fb` | `8561800` | docs(task1): remove 44 em dashes from the markdown artifacts |
| `f9b1728` | `96f21a5` | fix(checks): assert the snapshot's own integrity, not just its presence |
| `f9ef23b` | `635f670` | Add Task 3 harness artifact: reviewer-protocol.md |
| `fc25783` | `9962548` | Deploy the Task 2 report host so the critical-path worker does not have to |
| `fdb52b7` | `8cf7c85` | fix(types): clear the pyright debt instead of hiding it, and drop the exclusion |
| `fdd04b8` | `7c2e2ad` | Withdraw the pool-wide 429 claim; verify restart on the deployment |
