import paho.mqtt.client as mqtt
import time
import os
import json
import random

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
DRONE_ID = os.getenv("DRONE_ID", f"drone-{random.randint(100, 999)}")

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"[{DRONE_ID}] Connesso al broker MQTT.")

def run():
    client = mqtt.Client(client_id=DRONE_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    while True:
        try:
            client.connect(BROKER, PORT, 60)
            break
        except Exception:
            time.sleep(5)
            
    client.loop_start()
    
    try:
        while True:
            time.sleep(2)
            telemetry = {
                "id": DRONE_ID,
                "battery": random.randint(10, 100),
                "state": "IDLE"
            }
            client.publish("telemetry/drones", json.dumps(telemetry), qos=0)
            print(f"[{DRONE_ID}] Telemetria inviata: {telemetry}")
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    run()