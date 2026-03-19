import json
from collections import deque
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import os

BROKER_HOST = os.getenv("BROKER_HOST", "custom-broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "80"))
RECOMMENDATION_COOLDOWN_SECONDS = int(os.getenv("RECOMMENDATION_COOLDOWN_SECONDS", "20"))


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


def needs_attention(event: dict) -> bool:
    return event.get("battery", 100) < 20 or event.get("wear", 0.0) > 0.8


def get_queue_backlog() -> dict:
    try:
        resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/api/queues", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("queues", {})
    except Exception:
        return {}
    return {}


def build_recommendations(backlog: int, unhealthy_ratio: float) -> list:
    recommendations = []

    if backlog >= 20:
        add_drones = min(3, max(1, backlog // 20 + 1))
        recommendations.append(
            {
                "type": "PROPOSE_ADD_DRONES",
                "priority": "HIGH",
                "suggested_count": add_drones,
                "reason": f"Backlog ordini elevato ({backlog})",
            }
        )

    if backlog >= 10:
        timeout_seconds = 600 if unhealthy_ratio < 0.35 else 900
        recommendations.append(
            {
                "type": "PROPOSE_ORDER_TIMEOUT_POLICY",
                "priority": "MEDIUM",
                "timeout_seconds": timeout_seconds,
                "reason": f"Backlog sostenuto ({backlog}) con unhealthy_ratio={unhealthy_ratio:.2f}",
            }
        )

    if unhealthy_ratio >= 0.4:
        recommendations.append(
            {
                "type": "PROPOSE_MAINTENANCE_WINDOW",
                "priority": "HIGH",
                "reason": f"Percentuale droni in stato critico alta ({unhealthy_ratio:.2f})",
            }
        )

    return recommendations


def publish_recommendation(payload: dict):
    requests.post(
        f"http://{BROKER_HOST}:{BROKER_PORT}/publish/ops.recommendations",
        data=json.dumps(payload).encode("utf-8"),
        timeout=2,
    )


def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    recent_drone_health = deque(maxlen=50)
    last_emit_by_type = {}

    while True:
        try:
            resp = requests.get(f"http://{BROKER_HOST}:{BROKER_PORT}/consume/drone.events", timeout=2)
            if resp.status_code != 200:
                time.sleep(1)
                continue

            event = json.loads(resp.text)
            is_unhealthy = needs_attention(event)
            recent_drone_health.append(1 if is_unhealthy else 0)

            if is_unhealthy:
                print(f"fleet-agent: alert per {event.get('drone_id')}")

            if len(recent_drone_health) < 10:
                continue

            unhealthy_ratio = sum(recent_drone_health) / len(recent_drone_health)
            queue_sizes = get_queue_backlog()
            order_backlog = (
                queue_sizes.get("orders.incoming", 0)
                + queue_sizes.get("orders.normal", 0)
                + queue_sizes.get("orders.urgent", 0)
            )

            now = time.time()
            for rec in build_recommendations(order_backlog, unhealthy_ratio):
                rec_type = rec["type"]
                if now - last_emit_by_type.get(rec_type, 0) < RECOMMENDATION_COOLDOWN_SECONDS:
                    continue

                payload = {
                    "source": "fleet-agent-domain-controller",
                    "timestamp": now,
                    "order_backlog": order_backlog,
                    "unhealthy_ratio": round(unhealthy_ratio, 2),
                    "recommendation": rec,
                }
                publish_recommendation(payload)
                last_emit_by_type[rec_type] = now
                print(f"fleet-agent: recommendation emitted -> {rec_type}")
        except Exception as exc:
            print(f"fleet-agent: broker non disponibile ({exc})")
            time.sleep(2)


if __name__ == "__main__":
    main()
