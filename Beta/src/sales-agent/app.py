import json
import random
import time
import uuid
import requests
import redis
import os
import xml.etree.ElementTree as ET
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

# Handle Kubernetes putting 'tcp://ip:port' into REDIS_PORT when REDIS service is named redis
REDIS_PORT_RAW = os.getenv("REDIS_PORT", "6379")
if "://" in REDIS_PORT_RAW:
    REDIS_PORT = 6379 # Fallback if k8s env vars overwrote this with a URL string
else:
    REDIS_PORT = int(REDIS_PORT_RAW)
    

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

def get_redis_connection():
    while True:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
            if r.ping():
                print("Connected to Redis successfully!")
                return r
        except redis.ConnectionError as e:
            print(f"Waiting for Redis connection... {e} (Host: {REDIS_HOST}, Port: {REDIS_PORT})")
            time.sleep(2)

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    
    r = get_redis_connection()

    while True:
        try:
            resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/orders.incoming")
            if resp.status_code == 200:
                body = resp.text
                order_id = str(uuid.uuid4())
                
                # Assign Priority (XML manipulation)
                priority = random.choice(["URGENT", "NORMAL", "LOW"])
                
                root = ET.Element("order")
                ET.SubElement(root, "id").text = order_id
                ET.SubElement(root, "product").text = f"Product-{random.randint(100,999)}"
                ET.SubElement(root, "priority").text = priority
                
                payload = ET.tostring(root).decode('utf-8')
                
                # Publish to dashboard so the web UI stays updated
                try:
                    requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/dashboard.orders", data=payload)
                except Exception as e:
                    print(f"Stats warning: could not publish to dashboard - {e}")
                
                # Push back into queues
                if priority == "URGENT":
                    requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/orders.urgent", data=payload)
                    r.setex(f"order:urgent:{order_id}", 3600, payload) 
                else:
                    requests.post(f"http://{BROKER_HOST}:{BROKER_PORT}/publish/orders.normal", data=payload)
                    
            time.sleep(1)
        except requests.exceptions.RequestException:
            print("Broker non pronto...")
            time.sleep(2)

if __name__ == '__main__':
    main()
