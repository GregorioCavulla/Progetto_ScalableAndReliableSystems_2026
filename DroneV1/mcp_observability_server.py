#!/usr/bin/env python3

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp_layer import DroneMCP, ensure_data_files

OBS_TOOLS = {
    "get_fleet_snapshot",
    "get_open_orders",
    "estimate_order_cost",
    "plan_dispatch",
    "list_pending_approvals",
    "list_action_audit",
    "get_policy_limits",
}


def run_tool(mcp: DroneMCP, name: str, args: dict):
    if name not in OBS_TOOLS:
        return {"error": f"Tool {name} not allowed on observability server"}
    fn = getattr(mcp, name, None)
    if fn is None:
        return {"error": f"Tool {name} not found"}
    try:
        return fn(**args)
    except TypeError as exc:
        return {"error": f"Invalid args: {str(exc)}"}


def make_handler(mcp: DroneMCP):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "server": "observability"}, ensure_ascii=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if self.path != "/tool":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                payload = {}

            name = payload.get("name", "")
            args = payload.get("args", {})
            if not isinstance(args, dict):
                args = {}

            result = run_tool(mcp, name, args)
            body = json.dumps({"name": name, "result": result}, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args_):
            return

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DroneV1 MCP Observability Server")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8101, help="Bind port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_data_files(args.data_dir)
    mcp = DroneMCP(args.data_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(mcp))
    print(f"Observability MCP server on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
