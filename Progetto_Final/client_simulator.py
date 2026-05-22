import paho.mqtt.client as mqtt
import time
import os
import sys
import json
import random
import uuid
import argparse

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
CLIENT_ID = os.getenv("CLIENT_SIM_ID", f"client-sim-{random.randint(1, 100)}")

TOPIC_ORDINI = "business/ordini/nuovi"

# Area di copertura Hub (sistema di riferimento metrico in metri: HUB = [0, 0])
BASE_LAT = 0.0
BASE_LON = 0.0
RADIUS = 5000.0 

def generate_random_coordinate():
    lat = BASE_LAT + random.uniform(-RADIUS, RADIUS)
    lon = BASE_LON + random.uniform(-RADIUS, RADIUS)
    return round(lat, 2), round(lon, 2)


def get_priority(value_eur):
    if value_eur >= 100.0:
        return "high"
    if value_eur >= 50.0:
        return "normal"
    return "low"


def generate_order():
    pickup_lat, pickup_lon = generate_random_coordinate()
    drop_lat, drop_lon = generate_random_coordinate()
    order_value = round(random.uniform(10.0, 150.0), 2)
    
    order = {
        "order_id": f"ORD-{str(uuid.uuid4())[:8].upper()}",
        "status": "PENDING",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "drop_lat": drop_lat,
        "drop_lon": drop_lon,
        "weight_kg": round(random.uniform(0.5, 5.0), 2),
        "order_value_eur": order_value,
        "priority": get_priority(order_value),
        "timestamp": time.time()
        # TODO : aggiungere distribuzione uniforme di incasso per ogni ordine
    }
    return order

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"[{CLIENT_ID}]  Connesso al broker MQTT. Generazione ordini...")

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
    total_order_value = 0.0
    
    try:
        while True:
            # Crea un pacco / ordine ogni 10 - 25 secondi
            time.sleep(random.randint(10, 25))
            
            nuovo_ordine = generate_order()
            payload = json.dumps(nuovo_ordine)
            
            client.publish(TOPIC_ORDINI, payload, qos=1)
            total_order_value += nuovo_ordine["order_value_eur"]
            print(
                f" Nuovo Ordine Generato: {nuovo_ordine['order_id']} | Priorità: {nuovo_ordine['priority'].upper()} | Valore: {nuovo_ordine['order_value_eur']}€ | Totale accumulato: {total_order_value:.2f}€"
            )
            
    except KeyboardInterrupt:
        print(f"[{CLIENT_ID}] Spegnimento simulatore clienti...")
        print(f"[{CLIENT_ID}] Valore totale ordini generati: {total_order_value:.2f}€")
        client.loop_stop()
        client.disconnect()


def run_stress(total_orders: int = 50, delay_sec: float = 1.0):
    """Modalità stress-test: pubblica 'total_orders' ordini in rapida successione.
    Usata da chaos_test_suite.py (compatibilità Infrastructure_Bare).
    """
    client = mqtt.Client(client_id=f"stress-{CLIENT_ID}", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    while True:
        try:
            client.connect(BROKER, PORT, 60)
            break
        except Exception as e:
            print(f"Connessione fallita, broker non pronto: {e}. Riprovo in 5 sec...")
            time.sleep(5)

    client.loop_start()
    print(f"[{CLIENT_ID}] STRESS MODE: invio di {total_orders} ordini (delay {delay_sec}s).")
    try:
        for i in range(total_orders):
            nuovo_ordine = generate_order()
            payload = json.dumps(nuovo_ordine)
            client.publish(TOPIC_ORDINI, payload, qos=1)
            print(f"Ordine {i+1}/{total_orders} Generato: {nuovo_ordine['order_id']} | Priorità: {nuovo_ordine['priority'].upper()}")
            time.sleep(delay_sec)
        print(f"[{CLIENT_ID}] Stress test completato ({total_orders} ordini).")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Simulatore di clienti / generatore ordini.")
    parser.add_argument("--stress", action="store_true", help="Modalità stress-test: 50 ordini in 50 secondi.")
    parser.add_argument("--orders", type=int, default=50, help="Numero di ordini in stress mode.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay tra ordini in stress mode (secondi).")
    args = parser.parse_args()

    if args.stress:
        run_stress(total_orders=args.orders, delay_sec=args.delay)
    else:
        run()