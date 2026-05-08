import json
import os
import time
from threading import Thread

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Configurazione Ambiente ---
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
SERVER_ID = "central-server-node"
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))

TOPIC_TELEMETRY = "telemetry/drones"
TOPIC_ORDINI = "business/ordini/nuovi"
TOPIC_COMMANDS = "comandi/#"

# --- Configurazione InfluxDB ---
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "laboratorio")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_data")

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)
query_api = influx_client.query_api()

# Simula in memoria il Data Layer se DB non c'è, altrimenti qui inseriremo InfluxDB
state = {
    "drones": {},
    "pending_orders": [],
    "completed_orders": [],
    "assignments": {}
}

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Drone Fleet Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f4f6fb; color: #222; }
        header { background: #0d47a1; color: white; padding: 18px 24px; }
        header h1 { margin: 0; font-size: 1.7rem; }
        .subtitle { opacity: 0.84; margin-top: 6px; }
        .container { padding: 20px 24px; max-width: 1280px; margin: 0 auto; }
        .grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
        .card { background: white; border-radius: 14px; box-shadow: 0 12px 30px rgba(0,0,0,.06); padding: 18px; }
        .card h2 { margin-top: 0; font-size: 1.1rem; }
        .badge { display: inline-flex; padding: 4px 10px; border-radius: 999px; font-size: 0.85rem; font-weight: 700; }
        .badge.idle { background: #e8f0fe; color: #0d47a1; }
        .badge.in_delivery { background: #fff4e5; color: #e65100; }
        .badge.returning { background: #e0f2f1; color: #00695c; }
        .badge.maintenance { background: #fce4ec; color: #c2185b; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #e0e0e0; }
        th { color: #555; font-weight: 700; }
        .small { font-size: 0.95rem; color: #666; }
        .footer { margin-top: 18px; color: #555; font-size: 0.95rem; }
    </style>
</head>
<body>
    <header>
        <h1>Bombing Drone Fleet Dashboard</h1>
        <p class="subtitle">Monitoraggio in tempo reale di ordini, droni e consegne.</p>
    </header>
    <div class="container">
        <div class="grid">
            <div class="card">
                <h2>Snapshot</h2>
                <div id="snapshot"></div>
            </div>
            <div class="card">
                <h2>Broker e InfluxDB</h2>
                <div id="system-status"></div>
            </div>
        </div>
        <div class="grid">
            <div class="card">
                <h2>Ordini pendenti</h2>
                <div id="pending-orders"></div>
            </div>
            <div class="card">
                <h2>Droni attivi</h2>
                <div id="drone-list"></div>
            </div>
        </div>
        <div class="card">
            <h2>Ordini completati</h2>
            <div id="completed-orders"></div>
        </div>
        <div class="footer">
            Aggiornamento automatico ogni 5 secondi. Se il broker MQTT non risponde, verifica il servizio e la variabile di ambiente <code>MQTT_BROKER</code>.
        </div>
    </div>
    <script>
        function badgeClass(state) {
            if (state === 'IDLE') return 'badge idle';
            if (state === 'IN_DELIVERY') return 'badge in_delivery';
            if (state === 'RETURNING') return 'badge returning';
            return 'badge maintenance';
        }

        function renderSnapshot(data) {
            document.getElementById('snapshot').innerHTML = `
                <p class="small">Droni attivi: <strong>${data.drone_count}</strong></p>
                <p class="small">Ordini pendenti: <strong>${data.pending_orders}</strong></p>
                <p class="small">Ordini completati: <strong>${data.completed_orders}</strong></p>
            `;
        }

        function renderSystem(data) {
            document.getElementById('system-status').innerHTML = `
                <p class="small"><strong>MQTT Broker:</strong> ${data.mqtt_broker}</p>
                <p class="small"><strong>InfluxDB:</strong> ${data.influx_url}</p>
                <p class="small"><strong>Stato connessione:</strong> ${data.connected ? 'OK' : 'NON CONNESSO'}</p>
            `;
        }

        function renderOrders(orders) {
            if (!orders.length) {
                document.getElementById('pending-orders').innerHTML = '<p class="small">Nessun ordine pendente.</p>';
                return;
            }
            const rows = orders.map(order => `
                <tr>
                    <td>${order.order_id}</td>
                    <td>${order.priority}</td>
                    <td>${order.weight_kg}</td>
                </tr>
            `).join('');
            document.getElementById('pending-orders').innerHTML = `
                <table>
                    <thead><tr><th>ID Ordine</th><th>Priorità</th><th>Peso (kg)</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        }

        function renderDrones(drones) {
            if (!drones.length) {
                document.getElementById('drone-list').innerHTML = '<p class="small">Nessun drone connesso.</p>';
                return;
            }
            const rows = drones.map(drone => `
                <tr>
                    <td>${drone.id}</td>
                    <td><span class="${badgeClass(drone.state)}">${drone.state}</span></td>
                    <td>${drone.battery.toFixed(0)}%</td>
                    <td>${drone.lat.toFixed(5)}, ${drone.lon.toFixed(5)}</td>
                    <td>${drone.wear.toFixed(2)}</td>
                    <td>${drone.order_id || '-'}</td>
                </tr>
            `).join('');
            document.getElementById('drone-list').innerHTML = `
                <table>
                    <thead><tr><th>Drone</th><th>Stato</th><th>Batteria</th><th>Posizione</th><th>Usura</th><th>Ordine</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        }

        function renderCompleted(completed) {
            if (!completed.length) {
                document.getElementById('completed-orders').innerHTML = '<p class="small">Nessuna consegna registrata.</p>';
                return;
            }
            const rows = completed.map(item => `
                <tr>
                    <td>${item.order_id}</td>
                    <td>${item.drone_id}</td>
                    <td>${new Date(item.timestamp * 1000).toLocaleTimeString()}</td>
                </tr>
            `).join('');
            document.getElementById('completed-orders').innerHTML = `
                <table>
                    <thead><tr><th>ID Ordine</th><th>Drone</th><th>Completato</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        }

        async function refresh() {
            try {
                const [system, orders, drones, completed] = await Promise.all([
                    fetch('/api/status').then(r => r.json()),
                    fetch('/api/orders').then(r => r.json()),
                    fetch('/api/drones').then(r => r.json()),
                    fetch('/api/completed').then(r => r.json())
                ]);
                renderSnapshot(system);
                renderSystem(system);
                renderOrders(orders);
                renderDrones(drones);
                renderCompleted(completed);
            } catch (err) {
                document.getElementById('snapshot').innerHTML = '<p class="small">Impossibile aggiornare la dashboard.</p>';
                console.error(err);
            }
        }

        refresh();
        setInterval(refresh, 5000);
    </script>
</body>
</html>
"""


@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/drones')
def api_drones():
    drones = [
        {
            "id": drone_id,
            "state": data.get("state", "UNKNOWN"),
            "battery": float(data.get("battery", 0.0)),
            "lat": float(data.get("lat", 0.0)),
            "lon": float(data.get("lon", 0.0)),
            "wear": float(data.get("wear", 0.0)),
            "order_id": data.get("order_id")
        }
        for drone_id, data in state["drones"].items()
    ]
    return jsonify(drones)


@app.route('/api/orders')
def api_orders():
    return jsonify(state["pending_orders"])


@app.route('/api/completed')
def api_completed():
    return jsonify(state["completed_orders"])


@app.route('/api/status')
def api_status():
    return jsonify({
        "drone_count": len(state["drones"]),
        "pending_orders": len(state["pending_orders"]),
        "completed_orders": len(state["completed_orders"]),
        "mqtt_broker": BROKER,
        "influx_url": INFLUX_URL,
        "connected": True
    })


def record_assignment(topic, payload):
    if topic.startswith("comandi/"):
        try:
            if isinstance(payload, dict) and payload.get("action", "").upper() == "ASSIGN_MISSION":
                drone_id = topic.split('/', 1)[1]
                order_id = payload.get("order_id")
                if order_id:
                    state["assignments"][drone_id] = order_id
                    state["pending_orders"] = [o for o in state["pending_orders"] if o.get("order_id") != order_id]
                    print(f"📤 Ordine {order_id} assegnato a {drone_id}")
        except Exception as e:
            print(f"❌ Errore record assignment: {e}")


def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"🧠 [Server Centrale] Connesso al Broker MQTT. Ascolto su telemetria, ordini e comandi.")
    client.subscribe(TOPIC_TELEMETRY)
    client.subscribe(TOPIC_ORDINI)
    client.subscribe(TOPIC_COMMANDS)
    client.subscribe(TOPIC_COMMANDS)


def on_message(client, userdata, message, properties=None):
    try:
        topic = message.topic
        payload = json.loads(message.payload.decode("utf-8"))

        if topic.startswith("comandi/"):
            record_assignment(topic, payload)
            return

        if topic == TOPIC_TELEMETRY:
            drone_id = payload.get("id")
            previous = state["drones"].get(drone_id, {})
            previous_state = previous.get("state")
            state["drones"][drone_id] = payload

            if previous_state == "RETURNING" and payload.get("state") == "IDLE":
                assigned_order = state["assignments"].pop(drone_id, None)
                if assigned_order:
                    state["completed_orders"].append({
                        "order_id": assigned_order,
                        "drone_id": drone_id,
                        "timestamp": int(time.time())
                    })
                    print(f"✅ Ordine {assigned_order} consegnato da {drone_id}")

            point = (
                Point("drone_telemetry")
                .tag("drone_id", drone_id)
                .field("lat", float(payload.get("lat", 0.0)))
                .field("lon", float(payload.get("lon", 0.0)))
                .field("battery", float(payload.get("battery", 0.0)))
                .field("status", payload.get("state", "UNKNOWN"))
                .field("wear", float(payload.get("wear", 0.0)))
            )
            write_api.write(bucket=INFLUX_BUCKET, record=point)

        elif topic == TOPIC_ORDINI:
            order_id = payload.get("order_id")
            state["pending_orders"].append(payload)
            print(f"📥 [Server Centrale] Registrato Ordine {order_id} in coda (Totale pending: {len(state['pending_orders'])})")
            point = (
                Point("business_orders")
                .tag("order_id", order_id)
                .tag("priority", payload.get("priority", "normal"))
                .field("weight_kg", float(payload.get("weight_kg", 0.0)))
            )
            write_api.write(bucket=INFLUX_BUCKET, record=point)

    except Exception as e:
        print(f"❌ Errore processamento messaggio: {e}")

def connect_mqtt(client):
    hosts = [BROKER] + [h for h in ["localhost", "mqtt-broker", "mosquitto-service"] if h != BROKER]
    last_error = None
    for host in hosts:
        try:
            print(f"🔌 Provo broker MQTT {host}:{PORT}")
            client.connect(host, PORT, 60)
            print(f"✅ Connesso broker MQTT su {host}:{PORT}")
            return host
        except Exception as e:
            print(f"Connessione fallita a {host}:{PORT}: {e}")
            last_error = e
            time.sleep(2)
    raise ConnectionError(f"MQTT broker non raggiungibile su {hosts}: {last_error}")


def start_flask():
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)


def run():
    flask_thread = Thread(target=start_flask, daemon=True)
    flask_thread.start()

    client = mqtt.Client(client_id=SERVER_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    connect_mqtt(client)
    client.loop_start()

    try:
        print(f"🧠 [Server Centrale] In elaborazione continua in background... (dashboard su http://{FLASK_HOST}:{FLASK_PORT})")
        while True:
            time.sleep(15)
            print(f"\n--- SNAPSHOT SISTEMA ---")
            print(f"🚁 Droni tracciati: {len(state['drones'])}")
            print(f"📦 Ordini pendenti: {len(state['pending_orders'])}")
            print(f"✅ Consegne completate: {len(state['completed_orders'])}")
            print("------------------------\n")
    except KeyboardInterrupt:
        print("Spegnimento server...")
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    run()