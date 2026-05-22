import os
import json
import time
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, redirect
from kubernetes import client as k8s_client, config as k8s_config
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

app = Flask(__name__)
APPROVALS_FILE = Path("data/pending_approvals.jsonl")
AUDIT_FILE = Path("data/audit_actions.jsonl")
APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Init K8s (decoupled da DroneMCP: la dashboard chiama direttamente l'API K8s,
# stesso pattern di scale_drones.py)
_K8S_MODE = "NESSUNA"
try:
    k8s_config.load_incluster_config()
    _K8S_MODE = "in-cluster"
except Exception as e_in:
    try:
        k8s_config.load_kube_config()
        _K8S_MODE = "kubeconfig"
    except Exception as e_out:
        print(f"[K8S] FATAL: nessuna config caricabile (incluster: {e_in} | kubeconfig: {e_out})", flush=True)
print(f"[K8S] Config caricata: {_K8S_MODE}", flush=True)

# Bug kubernetes==36.0.0: load_incluster_config() popola api_key['authorization']
# ma auth_settings() della stessa lib cerca api_key['BearerToken'] -> nessun header
# inviato -> apiserver tratta la richiesta come system:anonymous -> 403.
# Workaround: leggiamo il token dal file SA e settiamo direttamente 'BearerToken'.
_k8s_cfg = k8s_client.Configuration.get_default_copy()
_sa_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
if _K8S_MODE == "in-cluster" and os.path.exists(_sa_token_path):
    with open(_sa_token_path) as _f:
        _tok = _f.read().strip()
    _k8s_cfg.api_key["BearerToken"] = _tok
    _k8s_cfg.api_key_prefix["BearerToken"] = "Bearer"
K8S_APPS = k8s_client.AppsV1Api(k8s_client.ApiClient(_k8s_cfg))

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-service")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _audit(action: str, details: dict):
    try:
        with open(AUDIT_FILE, "a") as f:
            f.write(json.dumps({"timestamp": int(time.time()), "action": action,
                                "payload": details, "source": "human_approval"}) + "\n")
    except Exception as e:
        print(f"Audit write failed: {e}")


def _exec_scale(replicas: int) -> dict:
    """Esegue lo scaling con chiamata K8s diretta (identico pattern di scale_drones.py)."""
    K8S_APPS.patch_namespaced_deployment_scale(
        name="drone-simulator",
        namespace="default",
        body={"spec": {"replicas": int(replicas)}}
    )
    _audit("approved_scale", {"replicas": int(replicas)})
    return {"status": "success", "replicas": int(replicas)}


def _exec_mqtt(target: str, action: str, **kwargs) -> dict:
    topic = f"comandi/{target}" if target != "all" else "comandi/tutti"
    payload = json.dumps({"action": action, **kwargs})
    c = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
                    client_id=f"approval-{int(time.time())}")
    c.connect(MQTT_BROKER, MQTT_PORT, 60)
    c.loop_start()
    c.publish(topic, payload, qos=1).wait_for_publish()
    c.loop_stop()
    c.disconnect()
    _audit("approved_mqtt", {"target": target, "action": action, "kwargs": kwargs})
    return {"status": "success", "topic": topic}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Human Approval Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: #fafafa; margin: 0; padding: 20px; color: #333; }
        header { background: #d32f2f; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { margin: 0; font-size: 1.5rem; }
        .grid { display: grid; gap: 15px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
        .card { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 5px solid #ff9800; }
        .card.approved { border-left-color: #4caf50; opacity: 0.8; }
        .card.rejected { border-left-color: #d32f2f; opacity: 0.8; }
        .card h2 { margin-top: 0; font-size: 1.2rem; }
        .card p { margin: 5px 0; font-size: 0.9rem; }
        pre { background: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 0.8rem; }
        .actions { margin-top: 15px; display: flex; gap: 10px; }
        button { border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; color: white; flex: 1; }
        .btn-approve { background: #4caf50; }
        .btn-approve:hover { background: #388e3c; }
        .btn-deny { background: #d32f2f; }
        .btn-deny:hover { background: #b71c1c; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; background: #fff3e0; color: #e65100; margin-bottom: 10px; }
        .badge.approved { background: #e8f5e9; color: #2e7d32; }
        .badge.rejected { background: #ffebee; color: #c62828; }
        .empty { text-align: center; padding: 40px; color: #777; font-style: italic; }
    </style>
</head>
<body>
    <header>
        <h1>Shield: Human Approval Gateway</h1>
        <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 0.9rem;">Intercetta i comandi AI distruttivi e applica il paradigma Operational Safety K8s.</p>
    </header>
    
    <div class="grid">
        {% if not approvals %}
            <div class="empty">Nessuna richiesta di operazione critica in attesa.</div>
        {% else %}
            {% for req in approvals %}
            <div class="card {{ req.status }}">
                <div class="badge {{ req.status }}">{{ req.status | upper }}</div>
                <h2>{{ req.action_type }}</h2>
                <p><strong>ID:</strong> {{ req.request_id }}</p>
                <p><strong>Motivo AI:</strong> {{ req.reason }}</p>
                <pre>{{ req.payload_str }}</pre>
                
                {% if req.status == 'pending' %}
                <div class="actions">
                    <form action="/api/approve/{{ req.request_id }}" method="POST" style="flex:1;">
                        <button type="submit" class="btn-approve">Approve</button>
                    </form>
                    <form action="/api/deny/{{ req.request_id }}" method="POST" style="flex:1;">
                        <button type="submit" class="btn-deny">Deny</button>
                    </form>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        {% endif %}
    </div>
    
    <script>
        // Ricarica la pagina in automatico se non abbiamo focus
        setInterval(() => {
            if (!document.hidden) window.location.reload();
        }, 5000);
    </script>
</body>
</html>
"""

def load_approvals():
    if not APPROVALS_FILE.exists():
        return []
    
    approvals = []
    try:
        with open(APPROVALS_FILE, "r") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line.strip())
                    item['payload_str'] = json.dumps(item.get('payload', {}), indent=2)
                    approvals.append(item)
    except:
        pass
    
    # Ordiniamo in modo che i pending siano primi, seguiti dai più recenti
    approvals.reverse()
    return approvals

def save_approvals(approvals):
    try:
        with open(APPROVALS_FILE, "w") as f:
            # Ripristiniamo l'ordine originario
            for item in reversed(approvals):
                cpy = dict(item)
                cpy.pop('payload_str', None)
                f.write(json.dumps(cpy) + "\n")
    except Exception as e:
        print(f"Errore scrittura JSONL: {e}")

@app.route("/")
def index():
    approvals = load_approvals()
    return render_template_string(HTML_TEMPLATE, approvals=approvals)

@app.route("/api/approve/<req_id>", methods=["POST"])
def approve(req_id):
    approvals = load_approvals()
    target = None
    for req in approvals:
        if req["request_id"] == req_id and req["status"] == "pending":
            target = req
            break

    if target is None:
        print(f"Approve: richiesta {req_id} non trovata o già processata")
        return redirect("/")

    # Esegui l'azione PRIMA di marcare lo stato: se K8s/MQTT falliscono
    # la richiesta resta pending e l'operatore può riprovare.
    try:
        action = target.get("action_type")
        payload = target.get("payload", {}) or {}
        if action == "scale_drone_deployment":
            result = _exec_scale(payload.get("replicas", 1))
        elif action == "send_mqtt_command":
            # estrae target/action dal payload e passa il resto come kwargs
            mqtt_target = payload.get("target", "all")
            mqtt_action = payload.get("action")
            extra = {k: v for k, v in payload.items() if k not in ("target", "action")}
            result = _exec_mqtt(target=mqtt_target, action=mqtt_action, **extra)
        else:
            print(f"Approve: action_type sconosciuto: {action}")
            return redirect("/")
        print(f"Approve {req_id} -> {result}")
    except Exception as e:
        print(f"Errore esecuzione azione approvata {req_id}: {e}")
        return redirect("/")

    target["status"] = "approved"
    save_approvals(approvals)
    return redirect("/")

@app.route("/api/deny/<req_id>", methods=["POST"])
def deny(req_id):
    approvals = load_approvals()
    for req in approvals:
        if req["request_id"] == req_id and req["status"] == "pending":
            req["status"] = "rejected"
            break
    save_approvals(approvals)
    return redirect("/")

if __name__ == '__main__':
    print(" Shield HTML Dashboard in ascolto sulla porta 5002...")
    APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=5002, debug=False)
