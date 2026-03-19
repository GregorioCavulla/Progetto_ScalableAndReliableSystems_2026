import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SRS_Remediation_V2")

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
BROKER_BASE_URL = f"http://{BROKER_HOST}:{BROKER_PORT}"

MAX_DRONE_DELTA = int(os.getenv("MCP_MAX_DRONE_DELTA", "5"))
MAX_ACTIONS_PER_INCIDENT = int(os.getenv("MCP_MAX_ACTIONS_PER_INCIDENT", "5"))
MAX_ESTIMATED_COST_DELTA = float(os.getenv("MCP_MAX_ESTIMATED_COST_DELTA", "250.0"))
MAX_APPROVAL_TTL_SECONDS = int(os.getenv("MCP_MAX_APPROVAL_TTL_SECONDS", "900"))

ALLOWED_ACTION_TYPES = {
    "ADD_DRONES",
    "SET_ORDER_TIMEOUT_POLICY",
    "SCHEDULE_MAINTENANCE_WINDOW",
    "ENABLE_DEGRADED_MODE",
    "REBALANCE_FLEET",
}

STATE_DIR = Path(os.getenv("MCP_STATE_DIR", "/tmp/mcp-remediation"))
STATE_FILE = STATE_DIR / "state.json"
AUDIT_LOG_PATH = Path(os.getenv("MCP_AUDIT_LOG_PATH", "/tmp/mcp-remediation/audit.log"))


def _ensure_state_files():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        initial = {"actions": {}, "incident_steps": {}}
        STATE_FILE.write_text(json.dumps(initial), encoding="utf-8")


_ensure_state_files()


def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"actions": {}, "incident_steps": {}}


def _save_state(state: Dict[str, Any]):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _audit(event: str, action_id: str, status: str, details: Dict[str, Any]):
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "action_id": action_id,
        "status": status,
        "details": details,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record) + "\n")

    try:
        requests.post(
            f"{BROKER_BASE_URL}/publish/ops.audit",
            data=json.dumps(record).encode("utf-8"),
            timeout=2,
        )
    except Exception:
        # Best effort: local audit log remains the source of truth.
        pass


def _publish_command(command_payload: Dict[str, Any]):
    requests.post(
        f"{BROKER_BASE_URL}/publish/ops.domain.commands",
        data=json.dumps(command_payload).encode("utf-8"),
        timeout=3,
    )


def _parse_parameters(parameters_json: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(parameters_json) if parameters_json else {}
    except json.JSONDecodeError:
        raise ValueError("parameters_json is not valid JSON")

    if not isinstance(parsed, dict):
        raise ValueError("parameters_json must decode to a JSON object")
    return parsed


def _validate_domain_action(action_type: str, parameters: Dict[str, Any]) -> str:
    if action_type == "ADD_DRONES":
        count = int(parameters.get("count", 0))
        if count < 1 or count > MAX_DRONE_DELTA:
            raise ValueError(
                f"ADD_DRONES requires count in range [1, {MAX_DRONE_DELTA}]"
            )
        return f"add {count} drones"

    if action_type == "SET_ORDER_TIMEOUT_POLICY":
        timeout_seconds = int(parameters.get("timeout_seconds", 0))
        order_class = parameters.get("order_class", "all")
        if timeout_seconds < 60 or timeout_seconds > 1800:
            raise ValueError("timeout_seconds must be in range [60, 1800]")
        if order_class not in {"all", "urgent", "normal"}:
            raise ValueError("order_class must be one of: all, urgent, normal")
        return f"set timeout={timeout_seconds}s for {order_class} orders"

    if action_type == "SCHEDULE_MAINTENANCE_WINDOW":
        duration_minutes = int(parameters.get("duration_minutes", 0))
        if duration_minutes < 5 or duration_minutes > 240:
            raise ValueError("duration_minutes must be in range [5, 240]")
        return f"schedule maintenance window for {duration_minutes} minutes"

    if action_type == "ENABLE_DEGRADED_MODE":
        strategy = parameters.get("strategy", "urgent_only")
        if strategy not in {"urgent_only", "throttle_non_urgent", "pause_non_urgent"}:
            raise ValueError(
                "strategy must be one of: urgent_only, throttle_non_urgent, pause_non_urgent"
            )
        return f"enable degraded mode strategy={strategy}"

    if action_type == "REBALANCE_FLEET":
        zone = parameters.get("zone")
        if not zone or not isinstance(zone, str):
            raise ValueError("REBALANCE_FLEET requires a non-empty zone string")
        return f"rebalance fleet toward zone={zone}"

    raise ValueError("Unsupported action type")


def _get_recommendations_snapshot(limit: int) -> Dict[str, Any]:
    resp = requests.get(
        f"{BROKER_BASE_URL}/api/queues/ops.recommendations/peek?limit={limit}",
        timeout=3,
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def get_pending_domain_recommendations(limit: int = 20) -> str:
    """Read-only inspection of domain recommendations generated by fleet-agent."""
    safe_limit = max(1, min(limit, 100))
    try:
        snapshot = _get_recommendations_snapshot(safe_limit)
    except Exception as exc:
        return f"Failed to read ops.recommendations: {exc}"

    items = snapshot.get("items", [])
    if not items:
        return "No pending domain recommendations."

    lines = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            lines.append(f"{idx}. raw={str(item)}")
            continue
        rec = item.get("recommendation", {})
        lines.append(
            f"{idx}. type={rec.get('type')} priority={rec.get('priority')} "
            f"reason={rec.get('reason')}"
        )
    return "\n".join(lines)


@mcp.tool()
def propose_domain_action(
    incident_id: str,
    action_type: str,
    target_scope: str,
    parameters_json: str,
    reason: str,
    estimated_monthly_cost_delta: float,
    risk_level: str = "HIGH",
) -> str:
    """Create a bounded domain proposal (orders/fleet). No execution happens in this step."""
    if action_type not in ALLOWED_ACTION_TYPES:
        return f"POLICY BLOCKED: unsupported action_type={action_type}"
    if not target_scope.strip():
        return "POLICY BLOCKED: target_scope must be non-empty"
    if estimated_monthly_cost_delta > MAX_ESTIMATED_COST_DELTA:
        return (
            "POLICY BLOCKED: estimated monthly cost delta exceeds configured budget guardrail "
            f"({MAX_ESTIMATED_COST_DELTA})."
        )

    risk_level = risk_level.upper().strip()
    if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        return "POLICY BLOCKED: risk_level must be one of LOW, MEDIUM, HIGH"

    try:
        parameters = _parse_parameters(parameters_json)
        policy_summary = _validate_domain_action(action_type, parameters)
    except ValueError as exc:
        return f"POLICY BLOCKED: {exc}"

    state = _load_state()
    action_id = str(uuid.uuid4())
    action = {
        "action_id": action_id,
        "incident_id": incident_id,
        "action_type": action_type,
        "target_scope": target_scope,
        "parameters": parameters,
        "risk_level": risk_level,
        "policy_summary": policy_summary,
        "reason": reason,
        "estimated_monthly_cost_delta": estimated_monthly_cost_delta,
        "status": "PROPOSED",
        "created_at": time.time(),
        "approved_by": None,
        "approval_token": None,
        "approval_expires_at": None,
        "executed_at": None,
    }

    state["actions"][action_id] = action
    _save_state(state)
    _audit("PROPOSE_DOMAIN_ACTION", action_id, "PROPOSED", action)

    return (
        f"Action proposed: action_id={action_id}. "
        "Requires explicit human approval before execution."
    )


@mcp.tool()
def approve_action(action_id: str, approver: str, approval_ttl_seconds: int = 300) -> str:
    """Grant time-bound human approval token for a proposed action."""
    ttl = max(30, min(approval_ttl_seconds, MAX_APPROVAL_TTL_SECONDS))

    state = _load_state()
    action = state.get("actions", {}).get(action_id)
    if not action:
        return f"NOT FOUND: action_id={action_id}"
    if action.get("status") != "PROPOSED":
        return f"POLICY BLOCKED: action is in status {action.get('status')} and cannot be approved."

    token = str(uuid.uuid4())
    now = time.time()
    action["status"] = "APPROVED"
    action["approved_by"] = approver
    action["approval_token"] = token
    action["approval_expires_at"] = now + ttl

    _save_state(state)
    _audit("APPROVE_ACTION", action_id, "APPROVED", {"approver": approver, "ttl": ttl})

    return (
        f"Approved action_id={action_id}. "
        f"approval_token={token} expires_in_seconds={ttl}"
    )


@mcp.tool()
def execute_approved_action(action_id: str, approval_token: str) -> str:
    """Execute a previously approved action with anti-loop and idempotency controls."""
    state = _load_state()
    action = state.get("actions", {}).get(action_id)
    if not action:
        return f"NOT FOUND: action_id={action_id}"

    status = action.get("status")
    if status == "EXECUTED":
        return f"IDEMPOTENT: action_id={action_id} already executed"
    if status != "APPROVED":
        return f"POLICY BLOCKED: action status must be APPROVED, found {status}"

    now = time.time()
    if action.get("approval_token") != approval_token:
        _audit("EXECUTE_ACTION", action_id, "BLOCKED", {"reason": "invalid_token"})
        return "POLICY BLOCKED: invalid approval token"
    if now > float(action.get("approval_expires_at", 0)):
        action["status"] = "EXPIRED"
        _save_state(state)
        _audit("EXECUTE_ACTION", action_id, "BLOCKED", {"reason": "token_expired"})
        return "POLICY BLOCKED: approval token expired"

    incident_id = action.get("incident_id", "default")
    current_steps = int(state.get("incident_steps", {}).get(incident_id, 0))
    if current_steps >= MAX_ACTIONS_PER_INCIDENT:
        _audit(
            "EXECUTE_ACTION",
            action_id,
            "BLOCKED",
            {
                "reason": "max_steps_exceeded",
                "incident_id": incident_id,
                "max_steps": MAX_ACTIONS_PER_INCIDENT,
            },
        )
        return (
            "POLICY BLOCKED: anti-loop threshold reached for incident "
            f"{incident_id}. Escalate to human operator."
        )

    command_payload = {
        "command_type": "DOMAIN_ACTION",
        "incident_id": incident_id,
        "action_type": action["action_type"],
        "target_scope": action["target_scope"],
        "parameters": action["parameters"],
        "risk_level": action["risk_level"],
        "issued_by": "mcp_remediation_v2",
        "approved_by": action.get("approved_by"),
        "action_id": action_id,
        "reason": action.get("reason"),
    }

    try:
        _publish_command(command_payload)
    except Exception as exc:
        _audit("EXECUTE_ACTION", action_id, "FAILED", {"error": str(exc)})
        return f"Execution failed while publishing command: {exc}"

    action["status"] = "EXECUTED"
    action["executed_at"] = now
    state.setdefault("incident_steps", {})[incident_id] = current_steps + 1
    _save_state(state)
    _audit("EXECUTE_ACTION", action_id, "EXECUTED", command_payload)

    return (
        f"EXECUTED: action_id={action_id}; action_type={action['action_type']}; "
        f"target_scope={action['target_scope']}"
    )


@mcp.tool()
def request_safe_fallback(incident_id: str, reason: str) -> str:
    """Record a rollback/escalation decision when confidence is low."""
    action_id = str(uuid.uuid4())
    payload = {
        "incident_id": incident_id,
        "fallback": "ESCALATE_TO_HUMAN",
        "reason": reason,
        "source": "mcp_remediation_v2",
    }
    _audit("SAFE_FALLBACK", action_id, "ESCALATED", payload)
    return "Fallback recorded: escalate to human operator and keep system in bounded mode."


@mcp.tool()
def get_action_status(action_id: str) -> str:
    """Read action status for auditing and post-incident review."""
    state = _load_state()
    action = state.get("actions", {}).get(action_id)
    if not action:
        return f"NOT FOUND: action_id={action_id}"
    safe_view = {
        "action_id": action.get("action_id"),
        "incident_id": action.get("incident_id"),
        "action_type": action.get("action_type"),
        "target_scope": action.get("target_scope"),
        "parameters": action.get("parameters"),
        "risk_level": action.get("risk_level"),
        "policy_summary": action.get("policy_summary"),
        "status": action.get("status"),
        "approved_by": action.get("approved_by"),
        "created_at": action.get("created_at"),
        "executed_at": action.get("executed_at"),
    }
    return json.dumps(safe_view)


if __name__ == "__main__":
    mcp.run()
