import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import json
import os
import time

# --- Configurazione Ambiente ---
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
SERVER_ID = "central-server-node"

TOPIC_TELEMETRY = "telemetry/drones"
TOPIC_ORDINI = "business/ordini/nuovi"

# --- Configurazione InfluxDB ---
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "laboratorio")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_data")

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# Simula in memoria il Data Layer se DB non c'è, altrimenti qui inseriremo InfluxDB
state = {
    "drones": {},
    "pending_orders": []
}

def on_connect(client, userdata, flags, rc):
    print(f"🧠 [Server Centrale] Connesso al Broker. Ascolto su telemetria e ordini.")
    client.subscribe(TOPIC_TELEMETRY)
    client.subscribe(TOPIC_ORDINI)

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode("utf-8"))
        
        if topic == TOPIC_TELEMETRY:
            # Aggiornamento stato flotta
            drone_id = payload.get("id")
            state["drones"][drone_id] = payload
            # Formattazione per InfluxDB
            point = (
                Point("drone_telemetry")
                .tag("drone_id", drone_id)
                .field("lat", float(payload.get("lat", 0.0)))
                .field("lon", float(payload.get("lon", 0.0)))
                .field("battery", float(payload.get("battery", 0.0)))
                .field("status", payload.get("state", "UNKNOWN"))
            )
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            
        elif topic == TOPIC_ORDINI:
            # Inserimento nuovo ordine in coda
            order_id = payload.get("order_id")
            state["pending_orders"].append(payload)
            print(f"📥 [Server Centrale] Registrato Ordine {order_id} in coda (Totale pending: {len(state['pending_orders'])})")
            
            # Formattazione ordine per InfluxDB (Eventi)
            point = (
                Point("business_orders")
                .tag("order_id", order_id)
                .tag("priority", payload.get("priority", "normal"))
                .field("weight_kg", float(payload.get("weight_kg", 0.0)))
            )
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            
    except Exception as e:
        print(f"❌ Errore processamento messaggio: {e}")

def run():
    client = mqtt.Client(client_id=SERVER_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    connected = False
    while not connected:
        try:
            client.connect(BROKER, PORT, 60)
            connected = True
        except Exception as e:
            print(f"Connessione fallita! Broker non pronto: {e}")
            time.sleep(5)
            
    client.loop_start()
    
    try:
        print("🧠 [Server Centrale] In elaborazione continua in background...")
        while True:
            # Un loop per stampare saltuariamente lo snapshot del sistema attuale
            time.sleep(15)
            drones_active = len(state["drones"])
            orders_pending = len(state["pending_orders"])
            print(f"\n--- SNAPSHOT SISTEMA ---")
            print(f"🚁 Droni tracciati: {drones_active}")
            print(f"📦 Ordini da assegnare: {orders_pending}")
            print("------------------------\n")
    except KeyboardInterrupt:
        print("Spegnimento server...")
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    run()