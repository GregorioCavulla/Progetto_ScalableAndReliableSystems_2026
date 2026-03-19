import logging
import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from typing import Dict, List

app = FastAPI()
queues: Dict[str, List[bytes]] = {}

# State in memory for the Dashboard
app_state = {
    "latest_orders": [],
    "drones": {},            # drone_id -> {lat, lon, battery, wear, status}
    "fleet_alerts": [],
    "human_intervention_required": False
}

logging.basicConfig(level=logging.INFO)

@app.post("/publish/{queue_name}")
async def publish(queue_name: str, request: Request):
    body = await request.body()
    
    # Intercetta eventi per la Dashboard
    if queue_name == "drone.events":
        try:
            data = json.loads(body.decode("utf-8"))
            did = data.get("drone_id")
            if did:
                app_state["drones"][did] = data
        except:
            pass
            
    elif queue_name == "dashboard.orders":
        # Ordine processato dal sales agent
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(body)
            app_state["latest_orders"].insert(0, {
                "id": root.findtext("id"),
                "product": root.findtext("product"),
                "priority": root.findtext("priority")
            })
            app_state["latest_orders"] = app_state["latest_orders"][:5] # Keep last 5
        except:
            pass
        return {"status": "ok"} # don't queue this one

    if queue_name not in queues:
        queues[queue_name] = []
    queues[queue_name].append(body)
    return {"status": "ok"}

@app.get("/consume/{queue_name}")
async def consume(queue_name: str):
    if queue_name not in queues or len(queues[queue_name]) == 0:
        return Response(status_code=404, content="Queue empty")
    payload = queues[queue_name].pop(0)
    return Response(content=payload)

@app.get("/api/state")
def get_state():
    # Ritorna lo stato inclusa la size delle code
    q_sizes = {k: len(v) for k,v in queues.items()}
    return {
        "queues": q_sizes,
        "state": app_state
    }

@app.post("/api/action/authorize")
def authorize_action():
    app_state["human_intervention_required"] = False
    return {"status": "authorized"}

@app.post("/api/action/trigger_lock")
def trigger_lock():
    # Endpoint da chiamare via MCP per chiedere intervento
    app_state["human_intervention_required"] = True
    return {"status": "locked"}

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Drone Logistics - Operational Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { background-color: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; }
            .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 0.5rem; padding: 1.5rem; }
            .pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        </style>
    </head>
    <body class="p-6">
        <div class="max-w-7xl mx-auto">
            <header class="flex justify-between items-center mb-8 border-b border-slate-700 pb-4">
                <h1 class="text-3xl font-bold text-emerald-400">SRS Control Center</h1>
                <div class="flex gap-4">
                    <div id="human-lock-banner" class="hidden bg-red-600/20 border border-red-500 text-red-400 px-4 py-2 rounded flex items-center gap-4">
                        <span class="pulse font-bold">⚠️ AGENT BLOCKED: Human Approval Required</span>
                        <button onclick="authorizeAction()" class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-sm transition">Authorize Action</button>
                    </div>
                </div>
            </header>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <!-- System Metrics -->
                <div class="card md:col-span-1">
                    <h2 class="text-xl font-semibold mb-4 text-slate-300">Broker Queues</h2>
                    <div id="queues-container" class="space-y-4"></div>
                    
                    <h2 class="text-xl font-semibold mt-8 mb-4 text-slate-300">Recent Orders</h2>
                    <div id="orders-container" class="space-y-2 text-sm text-slate-400"></div>
                </div>

                <!-- Drone Fleet -->
                <div class="card md:col-span-2">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-xl font-semibold text-slate-300">Active Drone Fleet</h2>
                        <span class="text-xs text-emerald-500 animate-pulse">● Live Telemetry</span>
                    </div>
                    <div id="drones-container" class="grid grid-cols-1 sm:grid-cols-2 gap-4"></div>
                </div>
            </div>
        </div>

        <script>
            async function fetchData() {
                try {
                    const res = await fetch('/api/state');
                    const data = await res.json();
                    renderQueues(data.queues);
                    renderOrders(data.state.latest_orders);
                    renderDrones(data.state.drones);
                    renderLocks(data.state.human_intervention_required);
                } catch (e) {
                    console.error("Dashboard error", e);
                }
            }

            function renderLocks(isLocked) {
                const banner = document.getElementById('human-lock-banner');
                if (isLocked) {
                    banner.classList.remove('hidden');
                } else {
                    banner.classList.add('hidden');
                }
            }

            function renderQueues(queues) {
                let html = '';
                for (const [q, count] of Object.entries(queues)) {
                    if (q.startsWith('dashboard')) continue;
                    let color = count > 20 ? 'text-red-400' : 'text-emerald-400';
                    html += `
                        <div class="flex justify-between items-center p-3 rounded bg-slate-800/50">
                            <span class="font-mono text-sm">${q}</span>
                            <span class="text-xl font-bold ${color}">${count}</span>
                        </div>
                    `;
                }
                document.getElementById('queues-container').innerHTML = html || '<p class="text-slate-500">No active queues.</p>';
            }

            function renderOrders(orders) {
                if (!orders || orders.length === 0) {
                    document.getElementById('orders-container').innerHTML = 'Waiting for orders...';
                    return;
                }
                let html = orders.map(o => `
                    <div class="flex border-l-2 border-emerald-500 pl-3 py-1 my-2">
                        <div>
                            <div class="font-mono text-white">${o.id}</div>
                            <div>Product: ${o.product} | Priority: ${o.priority}</div>
                        </div>
                    </div>
                `).join('');
                document.getElementById('orders-container').innerHTML = html;
            }

            function renderDrones(drones) {
                let html = '';
                for (const [id, d] of Object.entries(drones)) {
                    let batColor = d.battery < 20 ? 'text-red-500 font-bold pulse' : 'text-emerald-400';
                    let wearColor = d.wear > 0.8 ? 'text-orange-400' : 'text-slate-400';
                    html += `
                        <div class="p-4 rounded-lg bg-slate-800 border border-slate-700 hover:border-slate-500 transition">
                            <div class="flex justify-between mb-2">
                                <span class="font-mono font-bold text-white">${id}</span>
                                <span class="uppercase text-xs tracking-wider px-2 py-1 rounded bg-slate-900 border border-slate-600">${d.status}</span>
                            </div>
                            <div class="grid grid-cols-2 gap-2 text-sm">
                                <div class="text-slate-400">Battery: <span class="${batColor}">${d.battery}%</span></div>
                                <div class="text-slate-400">Wear: <span class="${wearColor}">${(d.wear * 100).toFixed(0)}%</span></div>
                            </div>
                        </div>
                    `;
                }
                document.getElementById('drones-container').innerHTML = html || '<p class="text-slate-500">No drones connected.</p>';
            }

            async function authorizeAction() {
                await fetch('/api/action/authorize', {method: 'POST'});
                fetchData();
            }

            setInterval(fetchData, 1000);
            fetchData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health")
def health():
    return "ok"
