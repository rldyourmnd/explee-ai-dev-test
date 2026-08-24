# Corpus candidates and their rights

Written after the evaluation design was frozen (commit `9fd6ff8`,
2026-08-23T19:00:14Z) and before any candidate was downloaded, so the corpus
cannot be chosen to suit an engine.
Corpus selection is the orchestrator's decision (`docs/briefs/orchestrator-mandate.md`);
this document supplies the evidence for it.

## The conditions the corpus must satisfy

From `PREREGISTRATION.md` §9, fixed in advance: natural (not scripted) Russian
speech, ~1 hour, dense English IT terminology code-switching *inside* sentences,
more than one speaker, real acoustics, and publication rights that let a grader
fetch the same recording and re-run the harness.

## Candidate A: Радио-Т (recommended)

Weekly Russian IT podcast, running since 2008, four regular hosts in a remote
call, ~1.5–2 h per episode, continuous unscripted technical discussion of
exactly the vocabulary in `glossary.json`.

* **Fit:** strong on every condition. Multiple speakers with overlap and
  interruption, telephone-grade remote acoustics with unequal levels, and
  code-switching inside almost every sentence. This is the hardest realistic
  case, not a favourable one.
* **Reproducibility:** episodes and MP3s are public at `radio-t.com/archives/`,
  so a grader can fetch the same file and check the SHA-256 in our manifest.
* **Rights, the real constraint.** The licence is **CC BY-NC-ND 3.0**, and the
  licence page states plainly that "modifications, mixes, edits and other
  additional creative work on our audio and texts are not permitted", while
  inviting people to ask for exceptions.
  ([radio-t.com/license](https://radio-t.com/license/))

  What that permits and forbids, read strictly:

  | Action | Position |
  |---|---|
  | Download and analyse privately | permitted, NC (a hiring exercise is non-commercial), no redistribution |
  | Cut into segments locally for scoring | a modification; kept **local**, never republished |
  | Send segments to a vendor API for transcription | processing under our control, not publication; mitigated by enabling no-retention / no-training options where the vendor exposes them, and recording per vendor whether it does |
  | Publish the segment files or the full reference transcript | **not done**: ND forbids it |
  | Publish metrics, short quoted spans as error examples, and the recipe (source URL, episode number, SHA-256, cut points) | done, citation, not redistribution |

  The report states this posture explicitly rather than leaving it implied, and
  the corpus is reproducible from the recipe: a reader fetches the same episode
  and re-cuts it with `harness/manifest.py`, obtaining our per-segment hashes.

* **Residual risk:** the ND clause is stricter than most CC licences and the
  cautious reading is that even local segmentation needs permission. The
  mitigation is to ask, since the licence page invites it, but a reply is not
  guaranteed inside this deadline.

## Candidate B: a conference talk with Q&A published under CC BY

A recorded Russian-language technical talk plus its audience Q&A, from a
conference that publishes under CC BY.

* **Fit:** good but weaker. A talk is semi-prepared speech, the speaker is
  usually alone until Q&A, and hall audio is cleaner than a meeting. It is a
  less demanding test than a meeting, which is the wrong direction for a
  benchmark meant to find where engines break.
* **Rights:** clean, CC BY permits derivatives with attribution, so segments
  and the full reference transcript could be published alongside the report.
* **Cost:** identifying an episode with verified CC BY licensing takes search
  time, and the licence must be verified per recording rather than per
  conference.

## Candidate C: Mozilla Common Voice Russian (rejected)

CC0, so rights are perfect, and it is rejected anyway: read sentences from a
prompt, one speaker per clip, no code-switching and no meeting acoustics. It
fails the one hard condition the employer set. Recording the rejection here so
the choice is visible: clean rights did not buy a relevant corpus.

## Recommendation

**Candidate A, with Candidate B prepared as a fallback if the ND clause is
judged to block even local segmentation.** A supplementary short scripted
passage may be added to probe specific terms, but per the brief it cannot be the
main corpus.

The decision needed from the orchestrator is which of A or B to freeze, and
whether to accept the ND reading above. Nothing has been downloaded, cut or sent
to any vendor.

## Environment blockers found while preparing (all local, all fixable)

Checked on this machine shortly before the freeze commit:

| Requirement | State | Consequence |
|---|---|---|
| `ffmpeg` / `ffprobe` | **absent** | the corpus cannot be probed or cut; hard blocker for the manifest |
| `yt-dlp` or equivalent | **absent** | needed only if the chosen source is a video platform |
| local ASR runtime | **absent** | needed for the two self-hosted engines |
| RAM | 8 GB, arm64 | Whisper large-v3 needs a quantised build (whisper.cpp) rather than the PyTorch checkpoint |

All are free, local installs and none requires a vendor account or spending.

## Correction to the engine slate

The brief and my own first pass treated Parakeet as an English-only baseline.
That was true of `parakeet-tdt-0.6b-v2`; **`parakeet-tdt-0.6b-v3` supports 25
European languages including Russian**
([model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)), so it is a
legitimate second self-hosted engine rather than a control. The two self-hosted
engines together mean the benchmark has a floor of two engines that need no
account, no payment details and no vendor permission.
