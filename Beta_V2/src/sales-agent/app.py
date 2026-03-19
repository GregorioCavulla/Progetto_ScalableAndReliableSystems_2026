import random
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import os

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))


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


def process_order(order_xml: str) -> bytes:
    root = ET.fromstring(order_xml)
    priority = root.findtext("priority") or random.choice(["URGENT", "NORMAL"])
    root.find("priority").text = priority
    return ET.tostring(root, encoding="utf-8")


def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    while True:
        try:
            consume = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/orders.incoming", timeout=2)
            if consume.status_code != 200:
                time.sleep(1)
                continue

            payload = process_order(consume.text)
            requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/dashboard.orders", data=payload, timeout=2)

            target = "orders.urgent" if b"URGENT" in payload else "orders.normal"
            requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/{target}", data=payload, timeout=2)
            print("sales-agent: ordine processato")
        except Exception as exc:
            print(f"sales-agent: broker non disponibile ({exc})")
            time.sleep(2)


if __name__ == "__main__":
    main()
