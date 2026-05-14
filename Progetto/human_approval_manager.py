import os
import json
import time
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, redirect
from drone_mcp_layer import DroneMCP

app = Flask(__name__)
mcp = DroneMCP()
APPROVALS_FILE = Path("data/pending_approvals.jsonl")

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
    for req in approvals:
        if req["request_id"] == req_id and req["status"] == "pending":
            req["status"] = "approved"
            # Eseguiamo immediatamente l'azione bypassando la policy dell'agente
            try:
                action = req.get("action_type")
                payload = req.get("payload", {})
                if action == "scale_drone_deployment":
                    result = mcp.scale_drone_deployment(replicas=payload.get("replicas", 1), force=True)
                    print(f"Scale result: {result}")
                elif action == "send_mqtt_command":
                    result = mcp.send_mqtt_command(target=payload.get("target", "all"), action=payload.get("action"), force=True, **payload)
                    print(f"MQTT command result: {result}")
            except Exception as e:
                print(f"Errore esecuzione azione approvata: {e}")
            break
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
