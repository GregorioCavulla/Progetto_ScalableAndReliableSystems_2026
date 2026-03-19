#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
MODEL="${MODEL:-qwen2.5:7b-instruct}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8090}"

DRONE_INTERVAL="${DRONE_INTERVAL:-0.5}"
ORDER_INTERVAL="${ORDER_INTERVAL:-0.8}"
AGENT_INTERVAL="${AGENT_INTERVAL:-12}"
AUTO_AGENT="${AUTO_AGENT:-1}"

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:11434/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}"

mkdir -p "$DATA_DIR"

DRONE_LOG="$DATA_DIR/drone_streamer.log"
ORDER_LOG="$DATA_DIR/order_streamer.log"
AGENT_ERR_LOG="$DATA_DIR/agent_errors.log"
AGENT_LAST_FILE="$DATA_DIR/last_agent_run.json"

PID_DRONE=""
PID_ORDER=""
PID_AGENT=""

cleanup() {
  echo
  echo "Stopping DroneDemo processes..."
  for pid in "$PID_AGENT" "$PID_ORDER" "$PID_DRONE"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

echo "Starting drone telemetry streamer..."
python3 "$ROOT_DIR/drone_streamer.py" \
  --data-dir "$DATA_DIR" \
  --ticks 100000000 \
  --interval "$DRONE_INTERVAL" \
  >>"$DRONE_LOG" 2>&1 &
PID_DRONE="$!"
echo "  drone_streamer pid=$PID_DRONE log=$DRONE_LOG"

echo "Starting order streamer..."
python3 "$ROOT_DIR/order_streamer.py" \
  --data-dir "$DATA_DIR" \
  --count 100000000 \
  --interval "$ORDER_INTERVAL" \
  >>"$ORDER_LOG" 2>&1 &
PID_ORDER="$!"
echo "  order_streamer pid=$PID_ORDER log=$ORDER_LOG"

if [[ "$AUTO_AGENT" == "1" ]]; then
  echo "Starting periodic LLM agent loop..."
  (
    while true; do
      TMP_FILE="$AGENT_LAST_FILE.tmp"
      python3 "$ROOT_DIR/agent_demo.py" \
        --data-dir "$DATA_DIR" \
        --model "$MODEL" \
        --max-steps 4 \
        >"$TMP_FILE" \
        2>>"$AGENT_ERR_LOG" || true
      if [[ -s "$TMP_FILE" ]]; then
        mv "$TMP_FILE" "$AGENT_LAST_FILE"
      fi
      sleep "$AGENT_INTERVAL"
    done
  ) &
  PID_AGENT="$!"
  echo "  agent_loop pid=$PID_AGENT out=$AGENT_LAST_FILE err=$AGENT_ERR_LOG"
else
  echo "AUTO_AGENT=0, periodic agent loop disabled."
fi

echo ""
echo "DroneDemo is starting."
echo "Dashboard URL: http://$HOST:$PORT"
echo "Open the dashboard and use 'Run Agent Now' for manual trigger if needed."
echo ""

echo "Startup checks (after 2s):"
sleep 2
curl -s "http://$HOST:$PORT/api/snapshot" >/dev/null && echo "  dashboard api: ok" || echo "  dashboard api: not reachable yet"
curl -s "${OPENAI_BASE_URL%/v1}/api/tags" >/dev/null && echo "  ollama api: ok" || echo "  ollama api: not reachable"
echo ""

python3 "$ROOT_DIR/dashboard.py" \
  --data-dir "$DATA_DIR" \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT"
