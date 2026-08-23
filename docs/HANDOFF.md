# Picking this up on another machine

## 1. Clone

```bash
git clone git@github.com:rldyourmnd/explee-ai-dev-test.git
cd explee-ai-dev-test
uv run --with pytest pytest tests/ -q     # expect all green
```

Requires `uv`, `gh` (authenticated), and SSH access to `server-nddev-amsterdam`.

## 2. Confirm the collector is still alive

This is the first thing to check on any machine, every time. The observation
window cannot be recreated.

```bash
ssh server-nddev-amsterdam '
  systemctl is-active explee-raw-sampler
  wc -l /opt/explee-spend-monitor/data/raw_samples.jsonl
  head -1 /opt/explee-spend-monitor/data/raw_samples.jsonl | python3 -c "import sys,json;print(\"T0:\",json.load(sys.stdin)[\"ts\"])"
  tail -1 /opt/explee-spend-monitor/data/raw_samples.jsonl | python3 -c "import sys,json;print(\"last:\",json.load(sys.stdin)[\"ts\"])"
'
```

Expect `active`, a line count growing by ~32 every 30 s, and a `last` timestamp
within the last minute. If it is not active, start it immediately and record the
gap in `docs/RUNLOG.md` — a gap is data, and hiding it would misrepresent the run.

## 3. Pull the captured data down

```bash
mkdir -p task1-spend-observability/data
rsync -avz server-nddev-amsterdam:/opt/explee-spend-monitor/data/raw_samples.jsonl \
  task1-spend-observability/data/
```

The `data/` directory is gitignored: it is large, it is reproducible from the
server, and the server copy is authoritative.

## 4. Export a trace when a task session ends

```bash
uv run tools/export_trace.py --list          # this project's sessions only
uv run tools/export_trace.py \
  --session <uuid> \
  --out task1-spend-observability/TRACE.md \
  --title "Task 1 — Spend Observability" \
  --copy-raw
```

**Do not pass `--max-result`.** It previously appeared here as
`--max-result 6000`, which was wrong: it truncates long tool results while the
generated header still claims nothing was dropped. A submission trace is required
to be verbatim, and a *disclosed* truncation is still not verbatim. Removed
2026-08-23T18:45Z after the external review found it.

Truncation is not the only lossless gap. Until `surface:8` closes them in the
exporter, an export can also drop image blocks behind an omission marker, skip
malformed JSONL records silently, and replace invalid UTF-8 rather than failing.
For a submission trace the exporter must **fail closed** — refuse to write —
whenever it cannot produce a lossless representation. Record the SHA-256 of the
source session JSONL alongside the exported trace so the export can be checked
against its input.

The exporter refuses to write if it finds a credential. That is intentional: fix
the source and re-export rather than editing the trace, which must stay verbatim.

## 5. Session boundaries

One Claude Code session per task, so each `TRACE.md` is a whole conversation
rather than a slice of one. The orchestration session that set the repository up
was exported to `TRACE-orchestration.md`; that file was quarantined for a
confidentiality leak and deleted from the working tree at 18:52Z, so it is not a
submission artifact and no longer exists at the root. See `AGENTS.md` rule 5.
