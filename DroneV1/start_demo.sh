#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
MODEL="${MODEL:-qwen2.5:7b-instruct}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8090}"

OBS_HOST="${OBS_HOST:-127.0.0.1}"
OBS_PORT="${OBS_PORT:-8101}"
OPS_HOST="${OPS_HOST:-127.0.0.1}"
OPS_PORT="${OPS_PORT:-8102}"

OBS_URL="http://$OBS_HOST:$OBS_PORT"
OPS_URL="http://$OPS_HOST:$OPS_PORT"
MCP_OPS_TOKEN="${MCP_OPS_TOKEN:-dronev1-token}"

DRONE_INTERVAL="${DRONE_INTERVAL:-0.5}"
ORDER_INTERVAL="${ORDER_INTERVAL:-0.8}"
AGENT_INTERVAL="${AGENT_INTERVAL:-15}"
AUTO_AGENT="${AUTO_AGENT:-1}"

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:11434/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}"
export MCP_OPS_TOKEN

mkdir -p "$DATA_DIR"

DRONE_LOG="$DATA_DIR/drone_streamer.log"
ORDER_LOG="$DATA_DIR/order_streamer.log"
OBS_LOG="$DATA_DIR/mcp_observability.log"
OPS_LOG="$DATA_DIR/mcp_operations.log"
AGENT_ERR_LOG="$DATA_DIR/agent_errors.log"

PID_DRONE=""
PID_ORDER=""
PID_OBS=""
PID_OPS=""
PID_AGENT=""

cleanup() {
  echo
  echo "Stopping DroneV1 processes..."
  for pid in "$PID_AGENT" "$PID_OPS" "$PID_OBS" "$PID_ORDER" "$PID_DRONE"; do
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
echo "  drone_streamer pid=$PID_DRONE"

echo "Starting order streamer..."
python3 "$ROOT_DIR/order_streamer.py" \
  --data-dir "$DATA_DIR" \
  --count 100000000 \
  --interval "$ORDER_INTERVAL" \
  >>"$ORDER_LOG" 2>&1 &
PID_ORDER="$!"
echo "  order_streamer pid=$PID_ORDER"

echo "Starting MCP observability server..."
python3 "$ROOT_DIR/mcp_observability_server.py" \
  --data-dir "$DATA_DIR" \
  --host "$OBS_HOST" \
  --port "$OBS_PORT" \
  >>"$OBS_LOG" 2>&1 &
PID_OBS="$!"
echo "  mcp_observability pid=$PID_OBS url=$OBS_URL"

echo "Starting MCP operations server..."
python3 "$ROOT_DIR/mcp_operations_server.py" \
  --data-dir "$DATA_DIR" \
  --host "$OPS_HOST" \
  --port "$OPS_PORT" \
  --token "$MCP_OPS_TOKEN" \
  >>"$OPS_LOG" 2>&1 &
PID_OPS="$!"
echo "  mcp_operations pid=$PID_OPS url=$OPS_URL"

if [[ "$AUTO_AGENT" == "1" ]]; then
  echo "Starting coordinator loop (Observer + Remediation)..."
  (
    while true; do
      python3 "$ROOT_DIR/agent_demo.py" \
        --obs-url "$OBS_URL" \
        --ops-url "$OPS_URL" \
        --ops-token "$MCP_OPS_TOKEN" \
        --model "$MODEL" \
        --observer-steps 3 \
        --remediation-steps 4 \
        --data-dir "$DATA_DIR" \
        2>>"$AGENT_ERR_LOG" >/dev/null || true
      sleep "$AGENT_INTERVAL"
    done
  ) &
  PID_AGENT="$!"
  echo "  agent_coordinator pid=$PID_AGENT"
else
  echo "AUTO_AGENT=0, periodic coordinator disabled."
fi

echo ""
echo "DroneV1 is starting."
echo "Dashboard URL: http://$HOST:$PORT"
echo "Observability MCP: $OBS_URL"
echo "Operations MCP: $OPS_URL"
echo ""

echo "Startup checks (after 2s):"
sleep 2
curl -s "$OBS_URL/health" >/dev/null && echo "  obs server: ok" || echo "  obs server: not reachable"
curl -s "$OPS_URL/health" >/dev/null && echo "  ops server: ok" || echo "  ops server: not reachable"
curl -s "${OPENAI_BASE_URL%/v1}/api/tags" >/dev/null && echo "  ollama api: ok" || echo "  ollama api: not reachable"
echo ""

python3 "$ROOT_DIR/dashboard.py" \
  --data-dir "$DATA_DIR" \
  --host "$HOST" \
  --port "$PORT" \
  --obs-url "$OBS_URL" \
  --ops-url "$OPS_URL" \
  --ops-token "$MCP_OPS_TOKEN" \
  --model "$MODEL"
