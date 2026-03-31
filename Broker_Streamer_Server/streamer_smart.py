#Droni

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import time
import os
import json
import random

broker = os.getenv("MQTT_BROKER", "mosquitto-service")
topic_pub = os.getenv("MQTT_TOPIC", "telemetry/smart")
topic_sub = "comandi/#"  # Il topic su cui questo sensore ascolterà gli ordini
pod_name = os.getenv("POD_NAME", f"smart-{random.randint(0, 100)}") # Se non c'è il nome del pod, ne generiamo uno casuale (utile per test locali)

# Funzione che scatta quando RICEVIAMO un messaggio
def on_message(client, userdata, message):
    comando = message.payload.decode("utf-8")
    print(f"\n🔔 [{pod_name}] RICEVUTO COMANDO su {message.topic}: {comando}\n")

# Funzione che scatta appena ci CONNETTIAMO (serve per iscriversi subito)
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connesso al broker! Mi iscrivo ai topic:")
    client.subscribe("comandi/tutti") # Comandi per tutti i sensori

    topic_personale = f"comandi/{pod_name}" # Comandi specifici per questo sensore
    client.subscribe(topic_personale)

    print(f"In ascolto su: {topic_personale} e comandi/tutti")

print(f"--- SENSOR SMART AVVIATO ({pod_name}) ---")

client = mqtt.Client(CallbackAPIVersion.VERSION2, pod_name)
client.on_message = on_message
client.on_connect = on_connect

client.connect(broker, 1883, 60)

# FONDAMENTALE: Avvia l'ascolto in background (non blocca il codice come loop_forever)
client.loop_start()

# Ciclo infinito di INVIO
while True:
    valore = round(random.uniform(20.0, 30.0), 2)
    payload = {"sender": pod_name, "value": valore, "timestamp": time.time()}
    
    try:
        client.publish(topic_pub, json.dumps(payload))
        print(f"Inviato: {valore}")
    except Exception as e:
        print(f"Errore invio: {e}")
        
    time.sleep(5) # Lo facciamo più lento (5 sec) così i log sono più puliti