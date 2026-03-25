import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import os
import sys

# Ora legge l'indirizzo interno dal cluster!
BROKER = os.getenv("MQTT_BROKER", "mosquitto-service")
PORT = 1883

def invia_comando(topic, messaggio):
    try:
        client = mqtt.Client(CallbackAPIVersion.VERSION2, "pannello-interno")
        client.connect(BROKER, PORT, 60)
        client.publish(topic, messaggio)
        print(f"\n🚀 [SUCCESSO] Comando inviato su '{topic}' -> {messaggio}\n")
        client.disconnect()
    except Exception as e:
        print(f"\n❌ [ERRORE] Qualcosa è andato storto: {e}\n")

if __name__ == "__main__":
    print("===================================")
    print("   🎛️  PANNELLO CONTROLLO INTERNO  ")
    print("===================================")
    print("1. 🟢 Accendi Ventola")
    print("2. 🔴 Spegni Ventola")
    print("3. 🔄 Riavvia Sensori (Gruppo B)")
    print("4. ✍️  Comando personalizzato...")
    print("0. ❌ Esci")
    print("===================================")
    
    scelta = input("Seleziona un'azione (0-4): ")
    
    if scelta == "1":
        invia_comando("comandi/ventola", "ACCENDI_VENTOLA")
    elif scelta == "2":
        invia_comando("comandi/ventola", "SPEGNI_VENTOLA")
    elif scelta == "3":
        invia_comando("comandi/riavvio", "RIAVVIO_SISTEMA")
    elif scelta == "4":
        topic_custom = input("Inserisci topic (es. comandi/luci): ")
        msg_custom = input("Inserisci messaggio: ")
        invia_comando(topic_custom, msg_custom)
    elif scelta == "0":
        sys.exit(0)
    else:
        print("Scelta non valida.")