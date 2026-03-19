import json
import time
import requests
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))

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

def evaluate_drone(drone_data):
    if drone_data["battery"] < 20 or drone_data["wear"] > 0.8:
        print(f"Agent Action: Drone {drone_data['drone_id']} Needs Maintenance!")

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    
    while True:
        try:
            resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/drone.events")
            if resp.status_code == 200:
                body = resp.text
                drone_data = json.loads(body)
                evaluate_drone(drone_data)
            else:
                time.sleep(1)
        except requests.exceptions.RequestException:
            print("Broker non pronto...")
            time.sleep(2)

if __name__ == '__main__':
    main()
