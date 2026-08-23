# The task, verbatim

Source: `https://jobs.explee.com/ai-native-developer/test`, captured
2026-08-23. This is the authority for every acceptance decision. Where our own
documents paraphrase it, they are wrong and this file is right.

---

# AI Dev Test Task

Three tasks below and how we want them delivered. Read the principles first —
they apply to all three.

## How we want you to work read this

Use AI. All of it. We are an AI-first, AI-native team. Driving AI agents and any
tooling you like is not just allowed here, it is the point. Do not hand-do
something an agent could do faster or better.

Be data-driven. Every conclusion is a hypothesis backed by data: "I think X is
happening, and here is the data that says so". Evidence beats opinion. If you
can not measure it, say so.

Send the agent trace. You will run an AI agent through each task. Export that
conversation as a TRACE.md per task, so we can follow how you got there. It must
be the REAL conversation — exported or copy-pasted as-is, every message and
every correction, verbatim. A hand-made "trace" tells us nothing.

## Task 1 — Spend Observability

We use ~15 external providers (proxies, LLM APIs, enrichment, ads, infra), each
with its own account. Give us a live picture of spend so that money does not run
out where we need to top up, and so we do not lose it unnoticed — we find out in
time.

What we give you: a live API that streams each provider's balance/spend in real
time. Base https://jobs.explee.com/ai-native-developer/test/api. No keys, no
signup — just call it. Catalog at GET /providers, one provider at
GET /<provider>/balance (both under the base URL). Each provider's response
shape is its own — read what actually comes back. There is no history endpoint,
only the current value.

Build: (1) a dashboard where one glance tells you what is happening with company
spend; (2) alerting — when your system decides a human should look, it appends a
line to alerts.jsonl.

The API behaves like a real third-party service, not a toy: sometimes slow,
sometimes an error, sometimes something odd. Dealing with that is part of the
task. It runs continuously — spend events happen on their own schedule, so the
longer you watch, the more you will see. Note: balances get topped up from time
to time — that is normal operations, not an incident.

Run your monitor for at least 6 hours (it runs in the background; longer = more
events = a fairer read). Every alert is one JSON line. Required keys: ts —
ISO-8601 with a timezone offset (or unix seconds; we grade across timezones, so
an offset-less time can only be read as UTC) and text. Recommended: provider.
Example:

```json
{"ts":"2026-08-20T14:03:11Z","provider":"openai","text":"spend ~4x above normal, sustained 20min"}
```

Send: the code (a file), your alerts.jsonl, a publicly deployed dashboard link
(opens without login), and TRACE.md.

## Task 2 — Pick the best transcriber for our meetings

Our meeting transcripts are constantly garbled: the engine hears "РАКа" instead
of RAG and "Lead House" instead of ClickHouse. Pick the best speech-to-text for
our speech. We do not trust other people's benchmarks — their audio is not ours.

The one hard condition: Russian speech with dense English and IT terminology
mixed in — product names, tools, vendors, people, jargon (code-switching). This
is exactly where the "universal" engines fall apart, and exactly what your test
must catch.

Build: a comparison of ≥5 STT engines of your choice on the same audio
(~1 hour), and the eval behind it — how you even measure "better/worse" on our
kind of speech. You set up the engines, keys and accounts yourself — budget a
few dollars for STT credits (an hour of audio across 5 engines is single-digit
dollars; free tiers cover most of it). Designing the eval IS the task: we will
not tell you the metric or hand you a recipe. Figuring out that a test is needed
and how to make it defensible is half the evaluation.

Send: a published comparison report (host it anywhere, send the link) — the
report is the main artifact — plus TRACE.md.

## Task 3 — Your best artifact

Attach the one harness artifact you are proudest of: a skill, a CLAUDE.md /
AGENTS.md, a slash command, a prompt, a hook — whatever you actually use to make
your work with AI agents better. One file, plus 2-3 lines on where it lives and
what it does.

Send: the file. This is a window into how you work day to day — taste and
maturity matter more than size.

## Submit

Send everything through the submission form: [ Submit your test task ]
