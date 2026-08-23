# Corpus freeze — Радио-Т, and the rules that chose it

Approved by the orchestrator at 2026-08-23T19:06Z, licence ruling at 19:10Z.
The span-selection rule below was **declared before the audio was cut and before
any of it was listened to**, so the span cannot have been chosen for favourable
material.

## Source

| Field | Value |
|---|---|
| Publisher | Радио-Т, `radio-t.com` |
| Episode | 1027, published 2026-08-22 |
| Source URL | `https://cdn.radio-t.com/rt_podcast1027.mp3` |
| SHA-256 of publisher original | `336a6c893b33c5f6281f8245a6cbd17d5bcaee8eb0d5a25a229e6807227dd8bb` |
| Bytes | 135 449 971 |
| Probed duration | 8463.218 s (2 h 21 m 03 s) |
| Probed format | MP3, 44 100 Hz, **mono**, 128 kbit/s |
| Retrieved | 2026-08-23, HTTP 200, plain HTTPS GET |

Everything in that table is measured (`curl -w`, `ffprobe`, `shasum -a 256`),
not quoted from the site.

## Episode-selection rule (declared before download)

> Take the most recent episode available at freeze time.

Episode 1027 was the most recent. No episode was auditioned, and no alternative
episode was downloaded or compared.

## Span-selection rule (declared before cutting)

> Take one contiguous 60-minute span beginning at 00:05:00, i.e. the source
> window `[300.0 s, 3900.0 s]`. The five-minute lead-in is skipped because a
> podcast opening is music, jingles and greetings rather than technical
> discussion; the offset is fixed in advance and not tuned.

Contiguous rather than sampled: a meeting transcript is judged on continuous
passages, and hand-picking scattered windows is the easiest way to flatter or
punish an engine without noticing.

Segmentation: uniform 30 s, giving **120 segments**, cut once and shared
byte-identically by every engine. Cut points are recorded as **absolute source
times**, so a reader re-derives the same segments from the publisher's file.

## Why this corpus, on the merits

Four hosts on a remote call: overlapping speech, interruption, unequal levels
and telephone-grade acoustics, with English IT terminology code-switched inside
Russian sentences almost continuously. It is the hardest realistic case rather
than a flattering one — which is the point. A good score on easy audio would
tell the employer nothing about the speech they actually have.

Note the source is **mono at 44.1 kHz**, so the frozen segments at 16 kHz mono
involve no downmix decision and no channel-handling asymmetry between engines:
one fewer confound, by luck rather than design.

## Licence: what we rely on, and where it is contestable

The episode is published under **CC BY-NC-ND 3.0**
([radio-t.com/license](https://radio-t.com/license/)), whose page states that
modifications, mixes and edits of the audio are not permitted, while inviting
exception requests.

**This must appear in the report body, not a footnote** (orchestrator ruling,
19:10Z):

* **What we publish:** metrics, short quoted error spans, and the recipe —
  episode number, source URL, SHA-256 of the publisher original, exact cut
  points. Nothing else.
* **What we do not publish:** the segment files, any processed audio, and the
  full reference transcript.
* **The ND leg is not in tension.** No derivative is distributed at all.
  Reproducibility comes from the recipe, verified against the *publisher's*
  file — which is stronger than shipping our own copy, because the reader
  checks us against the source rather than against ourselves.
* **The NC leg is the contestable one, and we say so plainly.** Creative Commons
  defines NonCommercial as not primarily directed toward commercial advantage or
  monetary compensation. A hiring submission is, at some remove, directed toward
  being paid. That is a real tension, not a technicality. We proceed because the
  only licence-governed act is a private download and local analysis — the
  posture academic benchmarking has long taken with NC corpora — and because the
  published artifact contains no licensed content: a measurement is a fact about
  a recording, not a reproduction of one.
* **The alternative was considered and rejected on the merits, not dodged.** A
  cleaner-licence corpus (CC BY conference talk) lacks overlapping speakers,
  remote-call acoustics and in-sentence code-switching, and would score engines
  on easy audio. The rejected analysis stays in `docs/corpus-candidates.md`.

Requesting a licence exception is an outward-facing communication and therefore
the human's call, not ours. It is flagged to them as an optional strengthener;
this work does not wait on it, and no one is contacted from here.

## Engine configuration change following this ruling

With Modal available on free credits, the 8 GB arm64 constraint no longer forces
quantisation. The self-hosted engines run **full-precision Whisper large-v3 and
Parakeet-TDT-0.6b-v3 on GPU** instead of the quantised whisper.cpp/int8 builds
adopted from meetily. This strengthens the comparison rather than merely
speeding it up: a local model that loses can no longer be excused as a casualty
of quantisation. meetily remains the cited source for the *model choice*; the
quantisation detail is now moot, and the change is recorded as an amendment in
`PREREGISTRATION.md` §12.

Modal discipline: one app created and named for this benchmark, every command
scoped to it by name, and the workspace never enumerated — it contains unrelated
deployments whose names must not reach a published trace.
