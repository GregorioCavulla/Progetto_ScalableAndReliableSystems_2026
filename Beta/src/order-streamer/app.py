import json
import logging
import os
import random
import string
import threading
import time
import requests
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
QUEUE_NAME = os.getenv("ORDER_QUEUE", "orders")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "1.0"))

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
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

def build_order_xml(order_id, product, quantity, distance_km, priority):
    order = ET.Element("order")
    ET.SubElement(order, "id").text = order_id
    ET.SubElement(order, "product").text = product
    ET.SubElement(order, "quantity").text = str(quantity)
    ET.SubElement(order, "distance_km").text = str(distance_km)
    ET.SubElement(order, "priority").text = str(priority)
    return ET.tostring(order, encoding="utf-8")

def generate_order():
    order_id = "ORD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    product = random.choice(["battery", "propeller", "sensor", "frame", "payload"])
    quantity = random.randint(1, 10)
    distance_km = random.randint(1, 50)
    priority = random.randint(1, 5)
    return build_order_xml(order_id, product, quantity, distance_km, priority)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_health_server()
    logging.info("Order streamer online, queue=%s", QUEUE_NAME)
    url = f"http://{BROKER_HOST}:{BROKER_PORT}/publish/{QUEUE_NAME}"
    while True:
        payload = generate_order()
        try:
            requests.post(url, data=payload, timeout=2)
            logging.info("Order published: %s", payload.decode("utf-8"))
        except Exception as e:
            logging.error("Failed to publish: %s", e)
        time.sleep(PUBLISH_INTERVAL)

if __name__ == "__main__":
    main()
