import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import json

# Configurazione MQTT
broker = os.getenv("MQTT_BROKER", "mosquitto-service")
topic = "telemetry/#"

# Configurazione InffluxDB
influx_url = os.getenv("INFLUX_URL", "http://influxdb-service:8086")
influx_token = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
influx_org = os.getenv("INFLUX_ORG", "laboratorio")
influx_bucket = os.getenv("INFLUX_BUCKET", "iot_data")

# Inizializzazioen client InfluxDB
influx_client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# Questa funzione viene chiamata ogni volta che arriva un messaggio
def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))
        sender = data.get("sender", "unknown")
        valore = data.get("value", 0)

        # Creiamo il "Punto" da salvare nel DB
        # 'measurement' è come il nome della tabella
        # 'tag' sono i metadati per filtrare velocemente (es. quale sensore)
        # 'field' è il dato vero e proprio
        point = (
            Point("ambiente")
            .tag("sensore", sender)
            .tag("tipo", message.topic.split("/")[-1])
            .field("valore", float(valore))
        )

        write_api.write(bucket=influx_bucket, record=point)
        print(f"Salvato su InfluxDB -> {sender}: {valore}")

    except Exception as e:
        print(f"Errore durante il salvataggio: {e}")


print("--- SERVER CENTRALE AVVIATO ---")

mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION2, "server-centrale")
mqtt_client.on_message = on_message
mqtt_client.connect(broker, 1883, 60)
mqtt_client.subscribe(topic)

# Questo tiene il programma in ascolto per sempre
mqtt_client.loop_forever()
