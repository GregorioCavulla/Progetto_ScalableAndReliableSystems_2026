#!/usr/bin/env python3

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agent_demo import LLMAgent
from mcp_layer import SimpleMCP, load_events_from_jsonl


def suggest_action_from_status(status):
  health = status.get("health")
  if health == "critical":
    return "restart_worker_simulated"
  if health == "degraded":
    return "clear_cache_simulated"
  return "no_action"


def build_snapshot(events_file, model, max_steps, temperature, with_agent, agent_refresh_s):
    events = load_events_from_jsonl(events_file)
    mcp = SimpleMCP(events)

    status = mcp.get_system_status(window=20)
    recent_events = mcp.get_recent_events(limit=12)
    recent_errors = mcp.get_recent_events(limit=8, state="error")

    agent_result = {
        "final_decision_text": "agent_disabled",
        "tool_trace": [],
    }

    if with_agent:
        now = time.time()
        if now - build_snapshot.last_agent_run >= agent_refresh_s:
            try:
                agent = LLMAgent(
                    mcp=mcp,
                    model=model,
                    max_steps=max_steps,
                    temperature=temperature,
                )
                build_snapshot.cached_agent_result = agent.run_once()
            except Exception as exc:  # pragma: no cover
                build_snapshot.cached_agent_result = {
                    "final_decision_text": "agent_error",
                    "tool_trace": [],
                    "error": str(exc),
                }
            build_snapshot.last_agent_run = now

        agent_result = build_snapshot.cached_agent_result

    return {
        "generated_at": int(time.time()),
        "events_total": len(events),
        "status": status,
        "recent_events": recent_events,
        "recent_errors": recent_errors,
        "agent": {
            "final_decision_text": agent_result.get("final_decision_text", "unknown"),
            "tool_trace": agent_result.get("tool_trace", []),
            "error": agent_result.get("error"),
        "suggested_human_action": suggest_action_from_status(status),
      },
      "human": {
        "last_action": build_snapshot.last_human_action,
        "last_result": build_snapshot.last_human_result,
        "last_action_at": build_snapshot.last_human_action_at,
        },
    }


build_snapshot.last_agent_run = 0.0
build_snapshot.cached_agent_result = {
    "final_decision_text": "not_run_yet",
    "tool_trace": [],
}
build_snapshot.last_human_action = "not_set"
build_snapshot.last_human_result = {}
build_snapshot.last_human_action_at = 0


def apply_human_action(action, events_file):
  events = load_events_from_jsonl(events_file)
  mcp = SimpleMCP(events)

  if action == "approve_remediation":
    result = mcp.run_remediation()
  elif action == "ignore_and_escalate":
    result = {"action": "escalate_to_human", "result": "acknowledged"}
  else:
    result = {"error": f"Unknown action: {action}"}

  build_snapshot.last_human_action = action
  build_snapshot.last_human_result = result
  build_snapshot.last_human_action_at = int(time.time())
  return result


HTML_PAGE = """<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SimpleDemo Dashboard</title>
    <style>
      :root {
        --bg: #f2f5f7;
        --card: #ffffff;
        --text: #1b2a34;
        --muted: #5f7482;
        --ok: #1c9d55;
        --warn: #d28516;
        --err: #c23a3a;
        --critical: #941f1f;
      }
      body { margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; background: radial-gradient(circle at 15% 10%, #e3eef3, var(--bg)); color: var(--text); }
      .wrap { max-width: 1200px; margin: 0 auto; padding: 20px; }
      h1 { margin: 0 0 4px 0; }
      .sub { color: var(--muted); margin-bottom: 16px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
      .card { background: var(--card); border-radius: 12px; padding: 14px; box-shadow: 0 2px 12px rgba(21,35,45,0.07); }
      .title { font-size: 13px; color: var(--muted); margin-bottom: 6px; }
      .value { font-size: 24px; font-weight: 700; }
      .health.healthy { color: var(--ok); }
      .health.degraded { color: var(--warn); }
      .health.critical { color: var(--critical); }
      .bar-box { margin-top: 8px; }
      .bar { height: 12px; border-radius: 8px; overflow: hidden; background: #e9eff3; display: flex; }
      .bar span { display: block; height: 100%; }
      .ok { background: var(--ok); }
      .warning { background: var(--warn); }
      .error { background: var(--err); }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      th, td { text-align: left; padding: 7px; border-bottom: 1px solid #edf1f4; vertical-align: top; }
      .row { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-top: 12px; }
      .mono { font-family: "Consolas", monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
      @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>SimpleDemo Dashboard</h1>
      <div class="sub">Aggiornamento automatico ogni 3 secondi</div>

      <div class="grid">
        <div class="card">
          <div class="title">System Health</div>
          <div id="health" class="value health">-</div>
        </div>
        <div class="card">
          <div class="title">Error Ratio</div>
          <div id="error_ratio" class="value">-</div>
        </div>
        <div class="card">
          <div class="title">Total Events</div>
          <div id="events_total" class="value">-</div>
        </div>
        <div class="card">
          <div class="title">Agent Final Decision</div>
          <div id="decision" class="value" style="font-size:18px;">-</div>
        </div>
      </div>

      <div class="card" style="margin-top: 12px;">
        <div class="title">State Distribution (window=20)</div>
        <div class="bar-box">
          <div class="bar">
            <span id="bar_ok" class="ok" style="width:0%"></span>
            <span id="bar_warning" class="warning" style="width:0%"></span>
            <span id="bar_error" class="error" style="width:0%"></span>
          </div>
        </div>
        <div id="counts" class="sub" style="margin-top:8px;margin-bottom:0;">-</div>
      </div>

      <div class="row">
        <div class="card">
          <div class="title">Recent Events</div>
          <table>
            <thead>
              <tr><th>timestamp</th><th>service</th><th>state</th><th>message</th><th>latency</th></tr>
            </thead>
            <tbody id="events_body"></tbody>
          </table>
        </div>
        <div class="card">
          <div class="title">Recent Errors</div>
          <table>
            <thead>
              <tr><th>timestamp</th><th>service</th><th>message</th></tr>
            </thead>
            <tbody id="errors_body"></tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top: 12px;">
        <div class="title">MCP Tool Trace (Agent)</div>
        <div id="tool_trace" class="mono">-</div>
      </div>

      <div class="card" style="margin-top: 12px;">
        <div class="title">Human In The Loop</div>
        <div class="sub" style="margin-bottom:10px;">
          Se l'agente decide <b>escalate_to_human</b>, puoi approvare o ignorare manualmente.
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button onclick="doHumanAction('approve_remediation')">Approve remediation</button>
          <button onclick="doHumanAction('ignore_and_escalate')">Ignore / keep escalated</button>
        </div>
        <div id="human_status" class="mono" style="margin-top:10px;">-</div>
      </div>
    </div>

    <script>
      function row(cells) {
        return "<tr>" + cells.map(c => "<td>" + c + "</td>").join("") + "</tr>";
      }

      async function doHumanAction(action) {
        const res = await fetch("/api/human_action?action=" + encodeURIComponent(action));
        const payload = await res.json();
        const text = JSON.stringify(payload, null, 2);
        document.getElementById("human_status").textContent = text;
        await refresh();
      }

      async function refresh() {
        const res = await fetch("/api/snapshot");
        const data = await res.json();

        const status = data.status || {};
        const counts = status.counts || {};
        const total = status.sample_size || 0;

        const ok = counts.ok || 0;
        const warning = counts.warning || 0;
        const error = counts.error || 0;

        const pOk = total ? (ok * 100 / total) : 0;
        const pWarning = total ? (warning * 100 / total) : 0;
        const pError = total ? (error * 100 / total) : 0;

        const healthEl = document.getElementById("health");
        healthEl.textContent = status.health || "unknown";
        healthEl.className = "value health " + (status.health || "unknown");

        document.getElementById("error_ratio").textContent = (status.error_ratio ?? 0).toFixed(3);
        document.getElementById("events_total").textContent = data.events_total;
        document.getElementById("decision").textContent = data.agent.final_decision_text || "n/a";

        document.getElementById("bar_ok").style.width = pOk.toFixed(1) + "%";
        document.getElementById("bar_warning").style.width = pWarning.toFixed(1) + "%";
        document.getElementById("bar_error").style.width = pError.toFixed(1) + "%";
        document.getElementById("counts").textContent = `ok=${ok} | warning=${warning} | error=${error}`;

        document.getElementById("events_body").innerHTML = (data.recent_events || []).map(e =>
          row([e.timestamp, e.service, e.state, e.message, e.latency_ms + " ms"])
        ).join("");

        document.getElementById("errors_body").innerHTML = (data.recent_errors || []).map(e =>
          row([e.timestamp, e.service, e.message])
        ).join("");

        const traceText = JSON.stringify(data.agent.tool_trace || [], null, 2);
        document.getElementById("tool_trace").textContent = traceText || "[]";

        const humanText = JSON.stringify({
          suggested_human_action: data.agent.suggested_human_action,
          last_action: data.human.last_action,
          last_result: data.human.last_result,
          last_action_at: data.human.last_action_at
        }, null, 2);
        document.getElementById("human_status").textContent = humanText;
      }

      refresh();
      setInterval(refresh, 3000);
    </script>
  </body>
</html>
"""


def make_handler(args):
  class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
      parsed = urlparse(self.path)

      if parsed.path == "/":
        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return

      if parsed.path == "/api/snapshot":
        snapshot = build_snapshot(
          events_file=args.events_file,
          model=args.model,
          max_steps=args.max_steps,
          temperature=args.temperature,
          with_agent=args.with_agent,
          agent_refresh_s=args.agent_refresh,
        )
        body = json.dumps(snapshot, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return

      if parsed.path == "/api/human_action":
        query = parse_qs(parsed.query)
        action = query.get("action", [""])[0]
        result = apply_human_action(action=action, events_file=args.events_file)
        body = json.dumps({"action": action, "result": result}, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return

      self.send_response(404)
      self.end_headers()

    def log_message(self, fmt, *args_):
      return

  return Handler


def parse_args():
    parser = argparse.ArgumentParser(description="Local dashboard for events + MCP + LLM agent")
    parser.add_argument("--events-file", required=True, help="Path to JSONL events file")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--with-agent", action="store_true", help="Run LLM agent periodically")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="Model served by Ollama")
    parser.add_argument("--max-steps", type=int, default=3, help="Max tool-calling steps for LLM")
    parser.add_argument("--temperature", type=float, default=0.0, help="Model temperature")
    parser.add_argument(
        "--agent-refresh",
        type=float,
        default=8.0,
        help="Minimum seconds between agent runs",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    handler = make_handler(args)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard running on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    server.serve_forever()


if __name__ == "__main__":
    main()