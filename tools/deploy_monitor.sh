#!/usr/bin/env bash
# Deploy monitor.py to the amsterdam host, correctly and verifiably.
#
# This exists because the sequence has subtleties that cost real time when done
# by hand, and one of them silently produced a wrong result:
#
#   1. Derived state must be dropped only while the container is STOPPED. The
#      running process holds the SQLite file open and its tail thread recreates
#      it, so `rm` then `restart` leaves the new process resuming from an offset
#      that should not exist. A deploy done that way replayed 16 records where a
#      full window was intended.
#
#   2. "Replay finished" cannot be detected by grepping the log for the serve
#      banner, because the PREVIOUS run's banner is still there. This counts
#      [replay] lines before starting and waits for the count to rise.
#
#   3. The raw sampler is never touched. It is checked before and after, and the
#      script aborts if it is not active. The observation window cannot be
#      recreated; no deployment is worth risking it.
#
# Usage:
#   tools/deploy_monitor.sh              # deploy, keep derived state
#   tools/deploy_monitor.sh --replay     # deploy and re-derive the whole window
set -euo pipefail

HOST="server-nddev-amsterdam"
UNIT="explee-raw-sampler"
CONTAINER="explee-spend-monitor"
STATE="/opt/explee-spend-monitor/state"
LOCAL_MONITOR="$(cd "$(dirname "$0")/.." && pwd)/task1-spend-observability/monitor.py"
REPLAY=false
[ "${1:-}" = "--replay" ] && REPLAY=true

mask() { sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip-redacted>/g'; }

before="$(ssh -o ConnectTimeout=30 "$HOST" "systemctl is-active $UNIT || true")"
echo "collector before : $before"
[ "$before" = "active" ] || { echo "collector is '$before' — aborting, the window is not recreatable" >&2; exit 1; }

echo "shipping monitor.py"
scp -q "$LOCAL_MONITOR" "$HOST:/opt/explee-spend-monitor/monitor.py"

local_sha="$(shasum -a 256 "$LOCAL_MONITOR" | cut -d' ' -f1)"
remote_sha="$(ssh -o ConnectTimeout=30 "$HOST" "sha256sum /opt/explee-spend-monitor/monitor.py | cut -d' ' -f1")"
[ "$local_sha" = "$remote_sha" ] || { echo "upload mismatch" >&2; exit 1; }
echo "deployed code matches local: ${local_sha:0:16}"

ssh -o ConnectTimeout=300 "$HOST" "
  set -e
  before_replays=\$(docker logs $CONTAINER 2>&1 | grep -c '\[replay\]' || echo 0)

  if $REPLAY; then
    # Stop FIRST. Deleting under a running process lets its tail thread
    # recreate the database before the restart takes effect.
    docker stop $CONTAINER >/dev/null
    cd $STATE
    [ -f alerts.jsonl ] && mv alerts.jsonl \"alerts.superseded.\$(date -u +%Y%m%dT%H%M%SZ).jsonl\" || true
    rm -f monitor.sqlite monitor.sqlite-wal monitor.sqlite-shm
    docker start $CONTAINER >/dev/null
  else
    docker restart $CONTAINER >/dev/null
  fi

  # Wait for THIS run's replay, not a banner left by the previous one.
  for i in \$(seq 1 60); do
    sleep 5
    now=\$(docker logs $CONTAINER 2>&1 | grep -c '\[replay\]' || echo 0)
    if [ \"\$now\" -gt \"\$before_replays\" ]; then
      echo \"replay completed after \$((i*5))s\"
      break
    fi
  done

  echo \"container : \$(docker inspect -f '{{.State.Status}}' $CONTAINER)\"
  docker logs $CONTAINER 2>&1 | grep '\[replay\]' | tail -1
  echo \"errors    : \$(docker logs $CONTAINER 2>&1 | grep -c '\[error\]' || echo 0)\"
  echo \"alerts    : \$(wc -l < $STATE/alerts.jsonl 2>/dev/null || echo 0) lines\"
  echo \"data mount: rw=\$(docker inspect $CONTAINER --format '{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.RW}}{{end}}{{end}}')\"
" 2>&1 | mask

after="$(ssh -o ConnectTimeout=30 "$HOST" "systemctl is-active $UNIT || true")"
restarts="$(ssh -o ConnectTimeout=30 "$HOST" "systemctl show $UNIT -p NRestarts --value")"
echo "collector after  : $after (NRestarts=$restarts)"
[ "$after" = "active" ] || { echo "collector is '$after' after deploy" >&2; exit 1; }

code="$(curl -sS -o /dev/null --max-time 25 -w '%{http_code}' https://spend.nddev.it.com/ || echo 000)"
echo "public dashboard : HTTP $code"
[ "$code" = "200" ] || { echo "public URL did not return 200" >&2; exit 1; }
echo "deploy verified"
