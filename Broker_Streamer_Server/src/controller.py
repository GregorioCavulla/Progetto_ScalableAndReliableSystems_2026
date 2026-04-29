import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import os
import sys
from kubernetes import client, config

BROKER = os.getenv("MQTT_BROKER", "mosquitto-service")
PORT = 1883

# Inizializza la connessione a Kubernetes usando la "Patente" del Pod
try:
    config.load_incluster_config()
    k8s_apps = client.AppsV1Api()
    k8s_core = client.CoreV1Api()
except Exception as e:
    print(f"Errore caricamento credenziali K8s: {e}")

def invia_comando(topic, messaggio):
    try:
        client_mqtt = mqtt.Client(CallbackAPIVersion.VERSION2, "pannello-interno")
        client_mqtt.connect(BROKER, PORT, 60)
        client_mqtt.publish(topic, messaggio)
        print(f"\n🚀 [SUCCESSO] Inviato su '{topic}' -> {messaggio}\n")
        client_mqtt.disconnect()
    except Exception as e:
        print(f"\n❌ [ERRORE MQTT]: {e}\n")

def ottieni_sensori():
    """Chiede a K8s in tempo reale la lista dei pod attivi"""
    try:
        pods = k8s_core.list_namespaced_pod(namespace="default", label_selector="app=sensore-b")
        return [pod.metadata.name for pod in pods.items if pod.status.phase == "Running"]
    except Exception as e:
        print(f"\n❌ [ERRORE K8S API]: {e}")
        return []

def scala_sensori(repliche):
    """Ordina a K8s di cambiare il numero di repliche del deployment"""
    try:
        body = {'spec': {'replicas': repliche}}
        k8s_apps.patch_namespaced_deployment_scale(
            name="app-sensore-b",
            namespace="default",
            body=body
        )
        print(f"\n✅ [SUCCESSO] Ordine inviato: Kubernetes sta portando i sensori a {repliche}!")
    except Exception as e:
        print(f"\n❌ [ERRORE K8S SCALE]: {e}")

if __name__ == "__main__":
    while True:
        print("\n===================================")
        print("   🎛️  PANNELLO KUBERNETES IoT     ")
        print("===================================")
        print("1. 📢 Accendi Ventola a TUTTI")
        print("2. 📢 Spegni Ventola a TUTTI")
        print("3. 🎯 Seleziona SINGOLO sensore")
        print("4. 📈 MODIFICA NUMERO SENSORI (Scale)")
        print("0. ❌ Esci")
        print("===================================")
        
        scelta = input("Seleziona un'azione: ")
        
        if scelta == "1":
            invia_comando("comandi/tutti", "ACCENDI_VENTOLA")
        elif scelta == "2":
            invia_comando("comandi/tutti", "SPEGNI_VENTOLA")
        elif scelta == "3":
            lista = ottieni_sensori()
            if not lista:
                continue
            
            print("\n--- SENSORI ONLINE ---")
            for i, sensore in enumerate(lista, start=1):
                print(f"[{i}] {sensore}")
            
            sub = input(f"\nSeleziona (1-{len(lista)} o 0 per annullare): ")
            if sub != "0" and sub.isdigit() and 1 <= int(sub) <= len(lista):
                target = lista[int(sub)-1]
                cmd = input(f"Comando per {target}: ")
                invia_comando(f"comandi/{target}", cmd)
                
        elif scelta == "4":
            print(f"\nSensori attualmente online: {len(ottieni_sensori())}")
            num = input("Quante repliche vuoi in totale? (es. 10): ")
            if num.isdigit():
                scala_sensori(int(num))
            else:
                print("Inserisci un numero valido.")
        elif scelta == "0":
            sys.exit(0)