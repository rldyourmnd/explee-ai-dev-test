# Self-hosted engine configuration, and what we took from meetily

Source: [`Zackriya-Solutions/meetily`](https://github.com/Zackriya-Solutions/meetily)
— a privacy-first local meeting assistant in Rust, starred by the employer, and
built for the same use case as this task: transcribing meetings on the user's
own machine. It is the right thing to learn from, because it is a real shipped
configuration rather than a benchmark author's guess.

We read its pipeline before adopting anything. What follows separates the parts
we take from the parts we deliberately refuse, with the reason for each.

## What meetily's pipeline actually does

| Stage | meetily's choice |
|---|---|
| ASR engine A | Whisper via `whisper-rs` (whisper.cpp), GGML quantised — `large-v3`, `large-v3-turbo`, quantisations `q5_0`/`q5_1`; Metal on macOS, CUDA or Vulkan elsewhere |
| ASR engine B | Parakeet via ONNX Runtime — `parakeet-tdt-0.6b-v3-int8`, `parakeet-tdt-0.6b-v2-int8` |
| Channels | downmix to mono |
| Resampling | 48 kHz (`SincFixedIn`) for capture; 16 kHz mono for the Whisper path |
| Microphone enhancement | 80 Hz high-pass, RNNoise suppression, EBU R128 loudness normalisation to −23 LUFS |
| Mixing | microphone + system audio, system pre-scaled to 70 % |
| Segmentation | Silero VAD, 30 ms frames, 250 ms minimum speech, 300/400 ms pre/post padding, long segments split at silence above 25 s |
| Terminology | none — no custom vocabulary, prompts or hotwords in the pipeline |
| Diarisation | none in the pipeline |

## What we adopt

**The engine configuration, and only that.**

* **Whisper `large-v3` via whisper.cpp, GGML `q5_0`, Metal.** This is the
  decisive practical finding: it makes a self-hosted large-v3 baseline runnable
  on this 8 GB arm64 laptop, which the PyTorch checkpoint is not. A shipped
  product choosing a quantised whisper.cpp build is better evidence that the
  configuration is usable than any benchmark of the full-precision checkpoint
  would be.
* **Parakeet `parakeet-tdt-0.6b-v3-int8` via ONNX Runtime.** Confirms the v3
  model (Russian-capable, unlike v2) runs int8 on CPU in real time — so the
  second self-hosted engine costs nothing and needs no GPU.

Both are cited in the report as taken from meetily. Neither changes what any
engine is *fed*: every engine, local and cloud, still receives byte-identical
segments from `harness/manifest.py`.

## What we refuse, and why

**meetily's audio preprocessing — RNNoise, the 80 Hz high-pass, EBU R128
normalisation, and Silero VAD segmentation — is not applied.**

Applying it would break the fairness rule this benchmark is built on, in the
most damaging way available: the local engines would receive cleaned, loudness-
normalised, speech-boundary-aligned audio, and the cloud engines would receive
the raw cut. Any advantage the local engines then showed would be an artefact of
preprocessing, and the report's central comparison would be worthless. The rule
in `PREREGISTRATION.md` §7 — identical source audio, segmentation, resampling
and channel handling for every engine — is not negotiable for a convenience.

Nor do we push meetily's chain onto the cloud engines to equalise it. Silero VAD
produces variable-length, speech-aligned segments; adopting it would change the
segmentation the corpus manifest was frozen with, and would hand every engine
a boundary hint that a real meeting deployment might or might not provide.

There is one more reason to refuse it that matters more than fairness:
**denoising and loudness normalisation are exactly the kind of transform that
can help one engine and hurt another**, and we do not know the sign in advance.
That is an empirical question, and the honest way to answer it is to measure it
rather than to bake it in.

## The measurable version: a labelled preprocessing side-experiment

Proposed to the orchestrator as an **addition**, not a change — it does not touch
the primary comparison, which stays on identical raw segments.

Run one self-hosted engine (Whisper `large-v3` q5_0) twice: once on the frozen
segments, once on the same segments after meetily's enhancement chain. Report
the paired difference with its bootstrap interval, as its own table titled
"effect of meetily-style preprocessing", never merged into the engine ranking.

It costs nothing — both runs are local — and it answers a question a reader will
actually have: *would cleaning the audio first have changed the answer?* If the
interval contains zero, that is a useful negative result and the report says so.

## Also reviewed

* **`digimata/quill`** (Swift, macOS recording + transcription) — a capture and
  UI layer. Nothing in it bears on engine configuration or scoring, so nothing
  is adopted.
* **`openai/whisper`** — the reference implementation; we run the quantised
  whisper.cpp build instead, per meetily, for the memory reason above. The model
  identity and snapshot are recorded either way.
* **`yt-dlp`** — needed only if the authorised corpus lives on a video platform.
  The recommended candidate (Радио-Т) publishes direct MP3s, so plain HTTPS
  retrieval suffices and one fewer tool enters the pipeline.

The employer's starred list was not enumerated here: the four relevant entries
were supplied directly, and dumping a full stars listing into a trace that ships
verbatim adds third-party detail this task has no use for. Same discipline as
`AGENTS.md` rule 3 — the scan that passes is evidence only for the pattern it
tested.

## Compute

Local first: both engines above are designed to run on this machine. **Modal** is
available with free credits if an hour of `large-v3` on CPU becomes the critical
path. If it is used, it will be a single app created and named for this
benchmark, and every command scoped to that app by name — the workspace is never
enumerated, because it contains unrelated deployments whose names must not reach
a published trace.
