import paho.mqtt.client as mqtt
import time
import os
import json
import random
import math

# --- Configurazione Ambiente ---
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
DRONE_ID = os.getenv("DRONE_ID", f"drone-{random.randint(100, 999)}")

TOPIC_PUB = "telemetry/drones"
TOPIC_SUB = f"comandi/{DRONE_ID}"

# Coordinate base (es. HUB centrale)
BASE_LAT = 0.0000
BASE_LON = 0.0000
RADIUS = 0.05

class Drone:
    def __init__(self, drone_id):
        self.id = drone_id
        self.lat = BASE_LAT 
        self.lon = BASE_LON
        self.battery = 100.0
        self.state = "IDLE" # Stati: IDLE, IN_DELIVERY, RETURNING, MAINTENANCE
        self.wear = 0.0 # Metrica di usura meccanica
        self.current_order = None
        self.target_lat = None
        self.target_lon = None
        self.speed = 0.001 # Spostamento in coordinate per "tick" (circa ~20-30 metri)
        self.battery_drain = 1 # Consumo batteria per tick in movimento
        # TODO: aggiungere scarica batteria e wear in base al peso dell'ordine e alla distanza percorsa

    def handle_command(self, payload):
        """Gestisce i comandi provenienti dal sistema centrale (MCP)"""
        try:
            data = json.loads(payload)
            
            # FIX BUG 1: Forziamo la stringa in minuscolo (.lower()) così 
            # ignoriamo se l'IA scrive "ASSIGN_MISSION" o "assign_mission"
            command = data.get("action", "").lower()
            
            if command == "assign_mission" and self.state == "IDLE":
                self.current_order = data.get("order_id")
                
                # FIX BUG 2: Se l'IA non manda le coordinate, ne generiamo di nuove
                # in modo casuale entro il raggio (RADIUS)
                self.target_lat = data.get("target_lat") or (BASE_LAT + random.uniform(-RADIUS, RADIUS))
                self.target_lon = data.get("target_lon") or (BASE_LON + random.uniform(-RADIUS, RADIUS))
                
                self.state = "IN_DELIVERY"
                print(f"[{self.id}]  Missione accettata: Ordine {self.current_order} verso [{round(self.target_lat, 4)}, {round(self.target_lon, 4)}]")
                
            elif command == "return_to_base":
                self.target_lat = BASE_LAT
                self.target_lon = BASE_LON
                self.state = "RETURNING"
                self.current_order = None
                print(f"[{self.id}]  Richiamo d'emergenza, ritorno alla base.")
                
        except Exception as e:
            print(f"[{self.id}]  Errore parsing comando: {e}")

    def update(self):
        """Evolve lo stato interno del drone ad ogni ciclo di clock (tick)"""
        # Se in volo verso un obiettivo
        if self.state in ["IN_DELIVERY", "RETURNING"]:
            if self.target_lat is not None and self.target_lon is not None:
                # Calcolo vettore spostamento
                d_lat = self.target_lat - self.lat
                d_lon = self.target_lon - self.lon
                distance = math.sqrt(d_lat**2 + d_lon**2)
                
                if distance < self.speed:
                    # Obiettivo raggiunto
                    self.lat = self.target_lat
                    self.lon = self.target_lon
                    
                    if self.state == "IN_DELIVERY":
                        print(f"[{self.id}]  Consegna {self.current_order} completata. Torno alla base HUB.")
                        self.state = "RETURNING"
                        self.current_order = None
                        self.target_lat = BASE_LAT
                        self.target_lon = BASE_LON
                    else:
                        print(f"[{self.id}]  Tornato all'HUB. In ricarica e attesa.")
                        self.state = "IDLE"
                        self.target_lat = None
                        self.target_lon = None
                else:
                    # Spostamento lungo il vettore
                    self.lat += (d_lat / distance) * self.speed
                    self.lon += (d_lon / distance) * self.speed
                    self.battery -= self.battery_drain
                    self.wear += random.uniform(0.01, 0.05)
                    
                    # Controllo batteria esaurita
                    if self.battery <= 0:
                        self.battery = 0
                        self.state = "MAINTENANCE"
                        self.current_order = None
                        self.target_lat = None
                        self.target_lon = None
                        print(f"[{self.id}]  BATTERIA ESAURITA - Drone caduto in manutenzione alle coordinate {round(self.lat, 6)}, {round(self.lon, 6)}")
                        continue  # Salta il resto del loop per questo tick
        
        # Logica di ricarica quando fermo alla base
        if self.state == "IDLE" and self.battery < 100.0:
            self.battery = min(100.0, self.battery + 0.5)

        # Controllo usura
        if self.wear > 10.0 and self.state != "MAINTENANCE":
            self.state = "MAINTENANCE"
            print(f"[{self.id}] ️ USURA ELEVATA - Drone in manutenzione.")

    def get_telemetry(self):
        return {
            "id": self.id,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "battery": round(self.battery, 2),
            "wear": round(self.wear, 2),
            "state": self.state,
            "order_id": self.current_order,
            "timestamp": time.time()
        }

# --- Gestione MQTT ---
drone_instance = Drone(DRONE_ID)

def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"[{DRONE_ID}]  Connesso al broker MQTT. Sottoscrizione a: {TOPIC_SUB}")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    drone_instance.handle_command(payload)

def run():
    client = mqtt.Client(client_id=DRONE_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    connected = False
    while not connected:
        try:
            client.connect(BROKER, PORT, 60)
            connected = True
        except Exception as e:
            print(f"Connessione fallita! Broker non pronto: {e}. Riprovo in 5 sec...")
            time.sleep(5)
            
    client.loop_start()
    
    # Loop di fisica e telemetria
    try:
        while True:
            drone_instance.update()
            telemetry = drone_instance.get_telemetry()
            client.publish(TOPIC_PUB, json.dumps(telemetry))
            
            # Stampa di cortesia solo se rientra in log limitato
            print(f" Telemetria [{drone_instance.state}] | Batt: {round(drone_instance.battery)}% | Pos: {telemetry['lat']},{telemetry['lon']}")
            time.sleep(2.0)  # Frequenza generatore IoT (1 tick ogni 2 secondi)
    except KeyboardInterrupt:
        print(f"[{DRONE_ID}] Spegnimento forzato...")
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    run()