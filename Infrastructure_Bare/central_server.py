import json
import os
import time
from threading import Thread

import paho.mqtt.client as mqtt
from flask import Flask, jsonify
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "REDACTED_INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "laboratorio")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_data")

app = Flask(__name__)
stats = {"drones_msgs": 0, "orders_msgs": 0}

try:
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
except Exception as e:
    print(f"Errore InfluxDB: {e}")
    write_api = None

@app.route('/')
def health():
    return jsonify({"status": "running", "stats": stats, "broker": BROKER, "influx": INFLUX_URL})

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print("Connesso al broker MQTT.")
    client.subscribe("telemetry/drones")
    client.subscribe("business/ordini/nuovi")

def on_message(client, userdata, message, properties=None):
    payload = json.loads(message.payload.decode("utf-8"))
    
    if message.topic == "telemetry/drones":
        stats["drones_msgs"] += 1
        if write_api:
            point = Point("test_telemetry").tag("drone_id", payload.get("id")).field("battery", float(payload.get("battery", 0)))
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            
    elif message.topic == "business/ordini/nuovi":
        stats["orders_msgs"] += 1
        if write_api:
            point = Point("test_orders").tag("order_id", payload.get("order_id")).field("qty", 1)
            write_api.write(bucket=INFLUX_BUCKET, record=point)

def start_mqtt():
    client = mqtt.Client(client_id="central-server", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(BROKER, PORT, 60)
            break
        except Exception:
            time.sleep(5)
            
    client.loop_start()

if __name__ == '__main__':
    Thread(target=start_mqtt, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)