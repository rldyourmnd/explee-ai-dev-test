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
uv run tools/export_trace.py --list          # find the session uuid
uv run tools/export_trace.py \
  --session <uuid> \
  --out task1-spend-observability/TRACE.md \
  --title "Task 1 — Spend Observability" \
  --max-result 6000 --copy-raw
```

The exporter refuses to write if it finds a credential. That is intentional: fix
the source and re-export rather than editing the trace, which must stay verbatim.

## 5. Session boundaries

One Claude Code session per task, so each `TRACE.md` is a whole conversation
rather than a slice of one. The orchestration session that set the repository up
is exported to `TRACE-orchestration.md` at the root.
