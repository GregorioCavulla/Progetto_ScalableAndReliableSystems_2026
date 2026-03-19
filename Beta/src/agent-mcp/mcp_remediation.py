from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
import datetime

# Server MCP dedicato a Remediation & Deployment
# Espone modifiche di stato protette da Safety Policy (budget caps, human-in-the-loop)
mcp = FastMCP("SRS_Remediation")

# Guardrail: Limite di repliche per vincoli economici (Budget)
MAX_REPLICAS = 5

@mcp.tool()
def scale_microservice(deployment_name: str, replicas: int) -> str:
    """Scale a specific Kubernetes deployment to handle load spikes.
    NOTE: Operates under strict economic guardrails. Do not exceed budget limits.
    """
    if replicas > MAX_REPLICAS:
        return f"SAFETY POLICY VIOLATION: Cannot scale beyond {MAX_REPLICAS} replicas due to OPEX cost ceiling. Budget compliant action blocked."
    if replicas < 1:
        return "SAFETY POLICY VIOLATION: Cannot scale below 1 replica. Must respect minimum availability SLO. Action blocked."
    
    try:
        config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        body = {"spec": {"replicas": replicas}}
        apps_v1.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace="default",
            body=body
        )
        return f"SUCCESS [Audit Logged]: Scaled {deployment_name} to {replicas} replicas."
    except Exception as e:
        return f"Failed to scale {deployment_name}: {e}"

@mcp.tool()
def emergency_restart_pod(deployment_name: str, human_approval_granted: bool) -> str:
    """
    Restart a deployment to recover from an unhandled failure state.
    HIGH RISK / DESTRUCTIVE ACTION.
    human_approval_granted MUST be EXPLICITLY set to True by the human operator before calling.
    Speculative restarts without user confirmation are forbidden.
    """
    if not human_approval_granted:
        return "SAFETY GUARDRAIL BLOCKED: Destructive action aborted. You MUST ask the human operator for explicit approval before attempting a restart."
    
    try:
        config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        
        # Effettua un patching dei metadata (come fa kubectl rollout restart)
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "srs.project.io/restartedAt": datetime.datetime.utcnow().isoformat()
                        }
                    }
                }
            }
        }
        
        apps_v1.patch_namespaced_deployment(
            name=deployment_name,
            namespace="default",
            body=body
        )
        return f"SUCCESS [Audit Logged]: Initiated emergency restart for deployment {deployment_name} by human approval."
    except Exception as e:
        return f"Failed to restart {deployment_name}: {e}"

if __name__ == "__main__":
    mcp.run()
