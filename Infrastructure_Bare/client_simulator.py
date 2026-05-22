import paho.mqtt.client as mqtt
import time
import os
import json
import random

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
CLIENT_ID = os.getenv("CLIENT_SIM_ID", f"client-sim-{random.randint(1, 100)}")

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"[{CLIENT_ID}] Connesso al broker MQTT.")

def run():
    client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
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
            time.sleep(10)
            order = {"order_id": f"ORD-{random.randint(1000,9999)}"}
            client.publish("business/ordini/nuovi", json.dumps(order), qos=1)
            print(f"[{CLIENT_ID}] Ordine generato: {order['order_id']}")
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    run()