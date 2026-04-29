#Ordini

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import time
import os
import json
import random

# Configurazione
broker = os.getenv("MQTT_BROKER", "mosquitto-service")
topic = os.getenv("MQTT_TOPIC", "telemetry/default")
pod_name = os.getenv("POD_NAME", "unknown-pod")

print(f"--- STREAMER V3 AVVIATO ({pod_name}) ---")

# Inizializzazione Client (API v2)
client = mqtt.Client(CallbackAPIVersion.VERSION2, pod_name)

# Tentativo di connessione infinito finché il broker non risponde
connected = False
while not connected:
    try:
        print(f"Tentativo di connessione a {broker}...")
        client.connect(broker, 1883, 60)
        connected = True
        print("Connesso al broker!")
    except Exception as e:
        print(f"Errore di connessione: {e}. Riprovo tra 5 secondi...")
        time.sleep(5)

# Loop di invio messaggi
while True:
    valore = round(random.uniform(20.0, 30.0), 2)
    payload = {"sender": pod_name, "value": valore, "timestamp": time.time()}
    
    try:
        client.publish(topic, json.dumps(payload))
        print(f"Inviato su {topic}: {valore}")
    except Exception as e:
        print(f"Errore durante l'invio: {e}")
        
    time.sleep(2)	
