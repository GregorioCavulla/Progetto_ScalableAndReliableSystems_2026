#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
PORT="${PORT:-8090}"
OBS_PORT="${OBS_PORT:-8101}"
OPS_PORT="${OPS_PORT:-8102}"

echo "Scenario 1 - Operations MCP down (graceful degradation)"
START_TS=$(date +%s)
pkill -f "mcp_operations_server.py" || true
sleep 2
curl -s "http://127.0.0.1:${PORT}/api/run_agent" >/dev/null || true
END_TS=$(date +%s)
echo "  elapsed=$((END_TS-START_TS))s"

echo "Scenario 2 - Malformed order injection"
echo '{"timestamp":1,"order_id":"BROKEN","status":"queued"' >> "$DATA_DIR/orders.jsonl"
python3 "$ROOT_DIR/order_streamer.py" --data-dir "$DATA_DIR" --count 3 --interval 0.1 >/dev/null 2>&1

echo "Scenario 3 - Queue congestion simulation"
python3 "$ROOT_DIR/order_streamer.py" --data-dir "$DATA_DIR" --count 100 --interval 0.01 >/dev/null 2>&1
curl -s "http://127.0.0.1:${PORT}/api/snapshot" | head -c 220 && echo

echo "Scenario 4 - Ollama unreachable"
export OPENAI_BASE_URL="http://127.0.0.1:65535/v1"
curl -s "http://127.0.0.1:${PORT}/api/run_agent" >/dev/null || true
echo "  agent should fall back with error trace"

echo "Scenario 5 - Recovery: restart MCP operations"
python3 "$ROOT_DIR/mcp_operations_server.py" --data-dir "$DATA_DIR" --port "$OPS_PORT" --token "${MCP_OPS_TOKEN:-dronev1-token}" >/dev/null 2>&1 &
sleep 2
curl -s "http://127.0.0.1:${OPS_PORT}/health" && echo

echo "Failure scenarios completed."
