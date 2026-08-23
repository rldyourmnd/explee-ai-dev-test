# Notes field — draft

Paste the body below into the form's Notes box. Keep it as prose; the form is a
plain textarea. Update the two bracketed numbers when the final window is cut.

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
than shipping a file we had already disproven. The submitted log passes at
0 of [12] unreconciled.

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
