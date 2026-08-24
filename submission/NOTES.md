# Notes field

Paste the body below into the form's Notes box. Keep it as prose; the form is a
plain textarea.

No placeholders remain, and every figure below traces to a committed artifact:
the Task 2 numbers to the published report, the audit numbers to
`ALERT-AUDIT.md`. The audit sentence is written to describe the *class* of
finding rather than freeze a tally, because the window keeps growing and a
count written here would go stale between drafting and submitting, which is
exactly what happened to the sentence it replaced.

---

**What we are proud of.** The raw collector went live before any dashboard code
existed, because the API has no history endpoint and an interrupted observation
window cannot be rebuilt. Everything downstream replays that one append-only log,
so every threshold we later changed was re-tested against identical evidence
rather than against fresh data that happened to suit it.

The repository's most useful artifact has no field on this form:
`ALERT-AUDIT.md`. It replays the captured window, reconciles every evidence field
in every alert line, runs counterfactuals that remove a nearby top-up or reverted
blip to see whether the alert survives, and proves it did not mutate the file it
audits by hashing it before and after. The first run **failed**: 2 of 13 lines did
not reconcile, and one existed only because of a top-up, which the task calls
normal operations. We regenerated the artifact from a single frozen build rather
than shipping a file we had already disproven.

**The submitted log still does not pass the audit, and we would rather tell you
than have you find it.** It is 30 lines and two do not reconcile. Both are the
same class: a `package_exhaustion` alert re-firing when the materiality band had
not changed, so a line carrying no new information. Both were written about nine
hours before the fix for that landed, and replaying the whole window under the
current code produces none of them; the log is append-only, so the lines stay and
the audit keeps naming them. That is the behaviour we want from a gate.

What the task actually forbids is at zero and has stayed there: the top-up-caused
line the first audit found is gone, and no alert is caused solely by a top-up or
by a reverted blip. `uv run tools/alert_audit_doc.py --check` prints the current
verdict. If the window grows before you read this the count may differ, and the
class will not.

Task 2 has the same shape. We recommended Whisper large-v3 with a glossary
prompt, then found the score came from 19 of 99 segments where the model
collapsed into a short terminology-dense summary instead of transcribing. The
metric was being gamed, our own preferred configuration was the one gaming it,
and we withdrew the recommendation. The report has a section called *What changed
our mind*.

**Doubts, as numbers rather than adjectives.** The Task 2 reference is a human
transcript published by the conference, which makes it independent of every
engine we rank, but it is edited for readability: fillers and false starts are
gone. That inflates absolute WER for every engine, so our WER figures are not
comparable to published benchmarks. We infer the magnitude of that editing from
an insertion/deletion asymmetry; we did not measure it against a verbatim sample,
and we say so in the report. One hour of audio resolves only large differences:
our power simulation puts the detection probability for a 3-point difference at
roughly 8%, so we report close systems as indistinguishable rather than ranked.
Only Whisper entered the terminology-assisted track, so that track establishes a
configuration choice, not engine superiority. The coverage guardrail was amended
after outputs existed; it is labelled as a post-output amendment with its reason,
not presented as pre-registered.

The recommendation is deliberately conditional. Prompted large-v3-turbo reaches
term recall 0.609 and plants a fabricated term in 5 of 99 segments, including
writing `Kubernetics` over the real `Kubernetes`. Unprompted turbo fabricates
nothing and misses about two thirds of the terminology. In a meeting transcript a
fabricated term is worse than a missing one, because a reader notices a gap from
context but cannot tell an invented product name from a real one. So: prompted if
terminology review stays in the loop, unprompted if it does not. No tested
configuration is ready for unsupervised use on this speech.

**What we would cut.** The dashboard carries more per-provider detail than one
glance needs; if we rebuilt it we would push the poll-health and sample-count
columns behind an expander and keep the top line, the risk ordering and the
sparklines. On Task 2 we would spend the same budget on two shorter corpora with
different speakers instead of one 49-minute talk, because speaker diversity would
have told us more than the extra minutes did.

**Scope we declined on purpose.** Diarization and timestamp metrics: the task
asks which engine hears the speech, not who spoke, and scoring speaker labels
against a reference that does not validate them would have been worse than not
scoring them. Paid STT accounts: everything runs on self-hosted GPUs, which also
means you can re-run the entire benchmark yourself without buying anything.

`raw_sampler.py` is the bootstrap collector that has been capturing since T0; the
submitted `monitor.py` is self-sufficient and can poll, persist, alert and serve
on its own.
