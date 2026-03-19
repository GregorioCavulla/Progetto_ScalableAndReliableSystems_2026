import json
import os
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SRS_Observability_V2")

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
BROKER_BASE_URL = f"http://{BROKER_HOST}:{BROKER_PORT}"


def _get_json(path: str) -> Dict[str, Any]:
    resp = requests.get(f"{BROKER_BASE_URL}{path}", timeout=3)
    resp.raise_for_status()
    return resp.json()


def _read_audit_tail(max_lines: int = 30) -> List[Dict[str, Any]]:
    try:
        data = _get_json(f"/api/queues/ops.audit/peek?limit={max_lines}")
        items = data.get("items", [])
        return [item for item in items if isinstance(item, dict)]
    except Exception:
        return []


@mcp.tool()
def get_broker_health() -> str:
    """Read-only health check for the event broker."""
    try:
        resp = requests.get(f"{BROKER_BASE_URL}/health", timeout=2)
        if resp.status_code == 200:
            return "Broker health: ok"
        return f"Broker health check returned status {resp.status_code}"
    except Exception as exc:
        return f"Broker health check failed: {exc}"


@mcp.tool()
def get_queue_snapshot() -> str:
    """Read-only queue depth and traffic counters for triage and observability."""
    try:
        data = _get_json("/api/queues")
        queues = data.get("queues", {})
        published = data.get("total_published", 0)
        consumed = data.get("total_consumed", 0)

        ordered = sorted(queues.items(), key=lambda x: x[1], reverse=True)
        queue_desc = ", ".join([f"{name}={size}" for name, size in ordered]) or "no queues"
        return (
            "Queue snapshot: "
            f"published={published}, consumed={consumed}, queues=[{queue_desc}]"
        )
    except Exception as exc:
        return f"Queue snapshot failed: {exc}"


@mcp.tool()
def get_domain_risk_assessment() -> str:
    """Compute a simple domain risk level using order backlog and recommendation pressure."""
    try:
        data = _get_json("/api/queues")
        queues = data.get("queues", {})
        backlog = (
            queues.get("orders.incoming", 0)
            + queues.get("orders.normal", 0)
            + queues.get("orders.urgent", 0)
        )
        pending_recommendations = queues.get("ops.recommendations", 0)

        if backlog >= 25 or pending_recommendations >= 10:
            risk = "HIGH"
        elif backlog >= 10 or pending_recommendations >= 4:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return (
            f"Domain risk={risk}; order_backlog={backlog}; "
            f"pending_recommendations={pending_recommendations}."
        )
    except Exception as exc:
        return f"Domain risk assessment failed: {exc}"


@mcp.tool()
def read_recent_remediation_audit(max_lines: int = 30) -> str:
    """Read-only tail of the remediation audit log for incident traceability."""
    max_lines = max(1, min(max_lines, 200))
    records = _read_audit_tail(max_lines=max_lines)
    if not records:
        return "No remediation audit records available."

    formatted = []
    for rec in records:
        event = rec.get("event", "unknown")
        action_id = rec.get("action_id", "-")
        status = rec.get("status", "-")
        ts = rec.get("timestamp", "-")
        formatted.append(f"{ts} | event={event} | action={action_id} | status={status}")
    return "\n".join(formatted)


if __name__ == "__main__":
    mcp.run()
