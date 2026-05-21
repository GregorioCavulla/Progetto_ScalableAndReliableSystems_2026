import paho.mqtt.client as mqtt
import time
import os
import json
import random
import uuid

# --- Configurazione Ambiente ---
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
CLIENT_ID = os.getenv("CLIENT_SIM_ID", f"stress-test-{random.randint(1, 100)}")

TOPIC_ORDINI = "business/ordini/nuovi"

# Area di copertura Hub (sistema di riferimento metrico in metri: HUB = [0, 0])
BASE_LAT = 0.0
BASE_LON = 0.0
RADIUS = 5000.0 # circa 5km in metri

def generate_random_coordinate():
    lat = BASE_LAT + random.uniform(-RADIUS, RADIUS)
    lon = BASE_LON + random.uniform(-RADIUS, RADIUS)
    return round(lat, 2), round(lon, 2)

def generate_order():
    pickup_lat, pickup_lon = generate_random_coordinate()
    drop_lat, drop_lon = generate_random_coordinate()
    
    order = {
        "order_id": f"ORD-{str(uuid.uuid4())[:8].upper()}",
        "status": "PENDING",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "drop_lat": drop_lat,
        "drop_lon": drop_lon,
        "weight_kg": round(random.uniform(0.5, 5.0), 2),
        "priority": random.choices(["low", "normal", "high"], weights=[0.2, 0.6, 0.2])[0],
        "timestamp": time.time()
    }
    return order

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"[{CLIENT_ID}] Connesso al broker MQTT. Avvio stress test con 50 ordini...")

def run():
    client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    while True:
        try:
            client.connect(BROKER, PORT, 60)
            break
        except Exception as e:
            print(f"Connessione fallita, broker non pronto: {e}. Riprovo in 5 sec...")
            time.sleep(5)
            
    client.loop_start()
    
    try:
        for i in range(50):
            nuovo_ordine = generate_order()
            payload = json.dumps(nuovo_ordine)
            
            client.publish(TOPIC_ORDINI, payload, qos=1)
            print(f"Ordine {i+1}/50 Generato: {nuovo_ordine['order_id']} | Priorità: {nuovo_ordine['priority'].upper()}")
            
            time.sleep(1)  # Uno al secondo
        
        print("Stress test completato. 50 ordini generati.")
        
    except KeyboardInterrupt:
        print(f"[{CLIENT_ID}] Interrotto...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    run()