import json
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import os

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
DRONE_ID = f"DRONE-{uuid.uuid4().hex[:6].upper()}"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    server.serve_forever()


def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    while True:
        telemetry = {
            "drone_id": DRONE_ID,
            "battery": random.randint(15, 100),
            "wear": round(random.uniform(0.05, 0.95), 2),
            "status": random.choice(["FLYING", "IDLE", "CHARGING"]),
            "timestamp": time.time(),
        }
        try:
            requests.post(
                f"http://{BROKER_HOST}:{BROKER_PORT}/publish/drone.events",
                data=json.dumps(telemetry).encode("utf-8"),
                timeout=2,
            )
            print(f"drone-fleet: telemetria inviata {telemetry['drone_id']}")
        except Exception as exc:
            print(f"drone-fleet: broker non disponibile ({exc})")
        time.sleep(3)


if __name__ == "__main__":
    main()
