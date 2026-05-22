import os
from flask import Flask, request, jsonify
from drone_mcp_layer import DroneMCP

app = Flask(__name__)
mcp = DroneMCP()

# Token letto da env (popolato via Kubernetes Secret); fallback per esecuzione locale.
MCP_TOKEN = os.getenv("MCP_TOKEN", "REDACTED_MCP_TOKEN")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/tool", methods=["POST"])
def execute_tool():
    default_token = MCP_TOKEN
    token = request.headers.get("X-MCP-Token")
    
    data = request.json
    name = data.get("name")
    args = data.get("args", {})
    
    # Observer tools
    if name == "get_drones_status":
        result = mcp.get_drones_status()
        print(f"MCP: get_drones_status -> {result}")
        return jsonify({"result": result})
    elif name == "get_drones_telemetry":
        result = mcp.get_drones_telemetry(**args)
        print(f"MCP: get_drones_telemetry -> {result}")
        return jsonify({"result": result})
    elif name == "get_pending_orders":
        result = mcp.get_pending_orders(**args)
        print(f"MCP: get_pending_orders -> {result}")
        return jsonify({"result": result})
    
    # Remediation tools
    elif name == "send_mqtt_command":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        result = mcp.send_mqtt_command(**args)
        print(f"MCP: send_mqtt_command -> {result}")
        return jsonify({"result": result})
    elif name == "scale_drone_deployment":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        result = mcp.scale_drone_deployment(**args)
        print(f"MCP: scale_drone_deployment -> {result}")
        return jsonify({"result": result})
    elif name == "request_human_approval":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        result = mcp.request_human_approval(**args)
        print(f"MCP: request_human_approval -> {result}")
        return jsonify({"result": result})
    elif name == "check_pending_approvals":
        result = mcp.check_pending_approvals(**args)
        print(f"MCP: check_pending_approvals -> {result}")
        return jsonify({"result": result})
    
    return jsonify({"error": "tool not found"}), 404

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8101
    app.run(host="0.0.0.0", port=port)