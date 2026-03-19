from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
import redis
import os

# Server MCP dedicato al Telemetry & Observability
# Espone operazioni read-only che l'agente può usare liberamente e autonomamente
mcp = FastMCP("SRS_Observability")

@mcp.tool()
def get_pod_status(namespace: str = "default") -> str:
    """Get the status of all Kubernetes Pods. Useful to check for crashes or pending instances."""
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace)
        
        result = ["--- POD STATUS ---"]
        for p in pods.items:
            restarts = p.status.container_statuses[0].restart_count if p.status.container_statuses else 0
            result.append(f"Pod: {p.metadata.name} | Status: {p.status.phase} | Restarts: {restarts}")
        return "\n".join(result)
    except Exception as e:
        return f"Error connecting to Kubernetes: {e}"

@mcp.tool()
def check_redis_metrics() -> str:
    """Check observability metrics from Redis (e.g. amount of priority orders)."""
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        length = r.zcard("orders:priority")
        return f"Orders in priority queue: {length} (A high number might indicate system load or delay)"
    except Exception as e:
        return f"Warning: Redis is unreachable or port-forward is inactive: {e}"

@mcp.tool()
def read_drone_alerts_log() -> str:
    """Consumes the recent logs of the fleet-agent to check for anomalies like low battery or wear."""
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod("default", label_selector="app=fleet-agent")
        if not pods.items:
            return "No fleet-agent pod found."
        
        pod_name = pods.items[0].metadata.name
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace="default", tail_lines=20)
        return f"Recent anomalies:\n{logs}"
    except Exception as e:
        return f"Failed to retrieve logs: {e}"

if __name__ == "__main__":
    mcp.run()
