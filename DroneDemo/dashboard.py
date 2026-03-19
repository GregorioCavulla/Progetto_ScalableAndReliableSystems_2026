#!/usr/bin/env python3

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agent_demo import DroneLLMAgent
from mcp_layer import DroneMCP, ensure_data_files


def snapshot(mcp: DroneMCP) -> dict:
    return {
        "generated_at": int(time.time()),
        "fleet": mcp.get_fleet_snapshot(),
        "orders": mcp.get_open_orders(limit=50),
        "pending_approvals": mcp.list_pending_approvals(),
        "last_agent_result": snapshot.last_agent_result,
    }


snapshot.last_agent_result = {
    "final_decision_text": "agent_not_run",
    "tool_trace": [],
}


HTML = """<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>DroneDemo Dashboard</title>
  <style>
    :root {
      --bg: #edf2f4;
      --card: #ffffff;
      --text: #1f2d3a;
      --muted: #64798a;
      --ok: #1f9c5c;
      --warn: #cd7b00;
      --err: #c0392b;
      --accent: #1d6fa5;
    }
    body { margin: 0; font-family: \"Segoe UI\", Tahoma, sans-serif; background: radial-gradient(circle at 15% 10%, #dbe8ef, var(--bg)); color: var(--text); }
    .wrap { max-width: 1250px; margin: 0 auto; padding: 18px; }
    h1 { margin: 0 0 6px; }
    .sub { color: var(--muted); margin-bottom: 12px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
    .card { background: var(--card); border-radius: 12px; padding: 12px; box-shadow: 0 2px 10px rgba(31, 45, 58, 0.08); }
    .title { font-size: 13px; color: var(--muted); margin-bottom: 7px; }
    .value { font-size: 24px; font-weight: 700; }
    .healthy { color: var(--ok); }
    .degraded { color: var(--warn); }
    .critical { color: var(--err); }
    .row { display: grid; grid-template-columns: 1.3fr 1fr; gap: 12px; margin-top: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; border-bottom: 1px solid #ecf1f4; padding: 6px; vertical-align: top; }
    button { background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 8px 10px; cursor: pointer; }
    button.alt { background: #5f6f7a; }
    .mono { font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    @media (max-width: 1000px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>DroneDemo Dashboard</h1>
    <div class=\"sub\">Fleet operations, orders, LLM decisions, human approvals</div>

    <div class=\"grid\">
      <div class=\"card\"><div class=\"title\">Total Drones</div><div id=\"total_drones\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"title\">Ready Drones</div><div id=\"ready_drones\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"title\">Open Orders</div><div id=\"open_orders\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"title\">Pending Approvals</div><div id=\"pending_count\" class=\"value\">-</div></div>
    </div>

    <div class=\"card\" style=\"margin-top: 12px;\">
      <div class=\"title\">Agent</div>
      <div id=\"decision\" class=\"mono\">-</div>
      <div class=\"actions\">
        <button onclick=\"runAgent()\">Run Agent Now</button>
      </div>
    </div>

    <div class=\"row\">
      <div class=\"card\">
        <div class=\"title\">Fleet Snapshot</div>
        <table>
          <thead><tr><th>drone</th><th>status</th><th>battery</th><th>wear</th><th>position</th><th>wind</th></tr></thead>
          <tbody id=\"fleet_body\"></tbody>
        </table>
      </div>
      <div class=\"card\">
        <div class=\"title\">Open Orders</div>
        <table>
          <thead><tr><th>order</th><th>urgency</th><th>product</th><th>destination</th><th>status</th></tr></thead>
          <tbody id=\"orders_body\"></tbody>
        </table>
      </div>
    </div>

    <div class=\"card\" style=\"margin-top: 12px;\">
      <div class=\"title\">Human Approval Queue</div>
      <table>
        <thead><tr><th>request</th><th>kind</th><th>reason</th><th>payload</th><th>actions</th></tr></thead>
        <tbody id=\"approvals_body\"></tbody>
      </table>
    </div>

    <div class=\"card\" style=\"margin-top: 12px;\">
      <div class=\"title\">Tool Trace</div>
      <div id=\"trace\" class=\"mono\">[]</div>
    </div>
  </div>

  <script>
    function row(cells) {
      return \"<tr>\" + cells.map(c => \"<td>\" + c + \"</td>\").join(\"\") + \"</tr>\";
    }

    async function loadSnapshot() {
      const res = await fetch('/api/snapshot');
      const data = await res.json();

      const summary = (data.fleet || {}).summary || {};
      document.getElementById('total_drones').textContent = summary.total || 0;
      document.getElementById('ready_drones').textContent = summary.ready || 0;
      document.getElementById('open_orders').textContent = (data.orders || {}).total_open || 0;
      document.getElementById('pending_count').textContent = (data.pending_approvals || {}).count || 0;

      const decision = (data.last_agent_result || {}).final_decision_text || 'agent_not_run';
      document.getElementById('decision').textContent = decision;

      const drones = (data.fleet || {}).drones || [];
      document.getElementById('fleet_body').innerHTML = drones.map(d =>
        row([
          d.drone_id,
          d.status,
          d.battery_pct + '%',
          d.wear_pct + '%',
          '(' + d.lon + ', ' + d.lat + ')',
          d.wind
        ])
      ).join('');

      const orders = (data.orders || {}).orders || [];
      document.getElementById('orders_body').innerHTML = orders.map(o =>
        row([
          o.order_id,
          o.urgency,
          o.product,
          '(' + o.dest_lon + ', ' + o.dest_lat + ')',
          o.status
        ])
      ).join('');

      const pending = (data.pending_approvals || {}).items || [];
      document.getElementById('approvals_body').innerHTML = pending.map(a => {
        const actionHtml = `<button onclick="approveReq('${a.request_id}',1)">Approve</button> <button class="alt" onclick="approveReq('${a.request_id}',0)">Reject</button>`;
        return row([
          a.request_id,
          a.kind,
          a.reason,
          JSON.stringify(a.payload),
          actionHtml
        ]);
      }).join('');

      document.getElementById('trace').textContent = JSON.stringify((data.last_agent_result || {}).tool_trace || [], null, 2);
    }

    async function runAgent() {
      await fetch('/api/run_agent');
      await loadSnapshot();
    }

    async function approveReq(requestId, approved) {
      await fetch('/api/approval?request_id=' + encodeURIComponent(requestId) + '&approved=' + approved);
      await loadSnapshot();
    }

    loadSnapshot();
    setInterval(loadSnapshot, 4000);
  </script>
</body>
</html>
"""


def make_handler(args):
    mcp = DroneMCP(args.data_dir)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)

            if parsed.path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/snapshot":
                body = json.dumps(snapshot(mcp), ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/run_agent":
                try:
                    agent = DroneLLMAgent(
                        mcp=mcp,
                        model=args.model,
                        max_steps=args.max_steps,
                        temperature=args.temperature,
                    )
                    snapshot.last_agent_result = agent.run_once()
                except Exception as exc:  # pragma: no cover
                    snapshot.last_agent_result = {
                        "final_decision_text": "agent_error",
                        "tool_trace": [{"error": str(exc)}],
                    }

                body = json.dumps({"status": "ok"}, ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/approval":
                request_id = query.get("request_id", [""])[0]
                approved = query.get("approved", ["0"])[0] == "1"
                note = query.get("note", [""])[0]
                result = mcp.apply_human_decision(request_id=request_id, approved=approved, note=note)
                body = json.dumps(result, ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt, *args_):
            return

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DroneDemo dashboard")
    parser.add_argument("--data-dir", default="data", help="Directory with JSONL files")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8090, help="Bind port")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="Ollama model")
    parser.add_argument("--max-steps", type=int, default=4, help="Agent max steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Agent temperature")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_data_files(args.data_dir)
    handler = make_handler(args)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"DroneDemo dashboard on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
