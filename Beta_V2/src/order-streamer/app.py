import random
import string
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import os

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
ORDER_QUEUE = os.getenv("ORDER_QUEUE", "orders.incoming")


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


def build_order():
    root = ET.Element("order")
    ET.SubElement(root, "id").text = "ORD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    ET.SubElement(root, "product").text = random.choice(["battery", "sensor", "payload"])
    ET.SubElement(root, "priority").text = random.choice(["URGENT", "NORMAL", "LOW"])
    return ET.tostring(root, encoding="utf-8")


def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    url = f"http://{BROKER_HOST}:{BROKER_PORT}/publish/{ORDER_QUEUE}"

    while True:
        try:
            payload = build_order()
            requests.post(url, data=payload, timeout=2)
            print("order-streamer: ordine pubblicato")
        except Exception as exc:
            print(f"order-streamer: broker non disponibile ({exc})")
        time.sleep(1)


if __name__ == "__main__":
    main()
