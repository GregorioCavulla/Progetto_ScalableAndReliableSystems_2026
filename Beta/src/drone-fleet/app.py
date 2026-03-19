import json
import random
import time
import requests
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import uuid

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
DRONE_ID = f"DRONE-{uuid.uuid4().hex[:6].upper()}"

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
    server.serve_forever()

def sim_telemetry():
    battery = 100
    wear = 0.0
    while True:
        battery = max(0, battery - random.randint(1, 5))
        wear = min(1.0, wear + random.uniform(0.01, 0.05))
        
        if battery == 0:
            status = "CHARGING"
            battery = 100
            print(f"[{DRONE_ID}] In ricarica...")
        else:
            status = "FLYING"

        telemetry = {
            "drone_id": DRONE_ID,
            "battery": battery,
            "wear": wear,
            "latitude": 45.4642 + random.uniform(-0.01, 0.01),
            "longitude": 9.1900 + random.uniform(-0.01, 0.01),
            "status": status,
            "timestamp": time.time()
        }
        
        try:
            requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/drone.events", json=telemetry)
            print(f"[{DRONE_ID}] Inviata telemetria")
        except Exception as e:
            print(f"[{DRONE_ID}] Errore invio telemetria: {e}")
            
        time.sleep(3)

def sim_orders():
    # Cerca ordini dalla coda
    while True:
        try:
            # Sceglie a caso da quale coda prendere (prima urgent, se no normal)
            resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/orders.urgent")
            if resp.status_code != 200:
                resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/orders.normal")
                
            if resp.status_code == 200:
                print(f"[{DRONE_ID}] Elaborazione ordine: {resp.text}")
                time.sleep(5) # Simula consegna
                print(f"[{DRONE_ID}] Consegna completata")
            else:
                time.sleep(1)
        except Exception as e:
            time.sleep(2)
        
def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    
    # Aspetto un po' per non floddiare il broker
    time.sleep(random.uniform(0, 3))
    
    t1 = threading.Thread(target=sim_telemetry, daemon=True)
    t2 = threading.Thread(target=sim_orders, daemon=True)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()

if __name__ == '__main__':
    main()
