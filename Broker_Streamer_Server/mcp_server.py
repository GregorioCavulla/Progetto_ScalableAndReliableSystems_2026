from flask import Flask, request, jsonify
from iot_mcp_layer import IotMCP

app = Flask(__name__)
mcp = IotMCP()

@app.route("/tool", methods=["POST"])
def execute_tool():
    default_token = "segreto-universitario"
    # Basic token check for operativity (8102)
    # The observer (8101) might not send it, but we can accept it either way in this unified server
    token = request.headers.get("X-MCP-Token")
    
    data = request.json
    name = data.get("name")
    args = data.get("args", {})
    
    # Observer tools
    if name == "get_cluster_status":
        return jsonify({"result": mcp.get_cluster_status()})
    elif name == "get_telemetry_summary":
        return jsonify({"result": mcp.get_telemetry_summary(**args)})
    
    # Remediation tools
    elif name == "send_mqtt_command":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        return jsonify({"result": mcp.send_mqtt_command(**args)})
    elif name == "scale_sensor_deployment":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        return jsonify({"result": mcp.scale_sensor_deployment(**args)})
    elif name == "request_human_approval":
        if token != default_token: return jsonify({"result": {"error": "Unauthorized"}}), 403
        return jsonify({"result": mcp.request_human_approval(**args)})
    
    return jsonify({"error": "tool not found"}), 404

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8101
    app.run(host="0.0.0.0", port=port)
