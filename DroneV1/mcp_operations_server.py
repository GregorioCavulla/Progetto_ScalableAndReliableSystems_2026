#!/usr/bin/env python3

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp_layer import DroneMCP, ensure_data_files

OPS_TOOLS = {
    "validate_action",
    "assign_order",
    "send_to_charge",
    "send_to_repair",
    "request_human_approval",
    "apply_human_decision",
    "list_pending_approvals",
    "estimate_agent_cost",
}

WRITE_TOOLS = {
    "assign_order",
    "send_to_charge",
    "send_to_repair",
    "request_human_approval",
    "apply_human_decision",
}


def run_tool(mcp: DroneMCP, name: str, args: dict):
    if name not in OPS_TOOLS:
        return {"error": f"Tool {name} not allowed on operations server"}
    fn = getattr(mcp, name, None)
    if fn is None:
        return {"error": f"Tool {name} not found"}
    try:
        return fn(**args)
    except TypeError as exc:
        return {"error": f"Invalid args: {str(exc)}"}


def make_handler(mcp: DroneMCP, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "server": "operations"}, ensure_ascii=True).encode("utf-8")
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

            if name in WRITE_TOOLS and token:
                req_token = self.headers.get("X-MCP-Token", "")
                if req_token != token:
                    body = json.dumps({"name": name, "result": {"error": "Unauthorized write action"}}, ensure_ascii=True).encode("utf-8")
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

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
    parser = argparse.ArgumentParser(description="DroneV1 MCP Operations Server")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8102, help="Bind port")
    parser.add_argument("--token", default=os.getenv("MCP_OPS_TOKEN", ""), help="Optional token for write ops")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_data_files(args.data_dir)
    mcp = DroneMCP(args.data_dir)
    token = args.token.strip() or None
    server = ThreadingHTTPServer((args.host, args.port), make_handler(mcp, token))
    print(f"Operations MCP server on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
