#!/usr/bin/env python3

import os
import json
import time
from pathlib import Path
from kubernetes import client, config
from influxdb_client import InfluxDBClient
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

POLICY_LIMITS = {
    "max_drones_auto": 6, # Oltre 6 droni l'agente deve chiedere il permesso all'umano
    "requires_human_approval": ["SHUTDOWN_ALL", "REBOOT_SYSTEM", "FIRMWARE_UPDATE"],
    "cost_per_drone_eur": 0.05 # Costo fittizio per calcolare il budget
}

class DroneMCP:
    def __init__(self, data_dir="data"):

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.data_dir / "audit_actions.jsonl"
        self.approvals_file = self.data_dir / "pending_approvals.jsonl"

        # 1. Setup Kubernetes
        try:
            config.load_incluster_config() 
        except:
            try:
                config.load_kube_config() 
            except Exception as e:
                print(f"️ Avviso K8s: Impossibile caricare configurazione ({e})")
        
        self.k8s_apps = client.AppsV1Api()
        self.k8s_core = client.CoreV1Api()

        # 2. Setup InfluxDB
        self.influx_url = os.getenv("INFLUX_URL", "http://localhost:8086")
        self.influx_token = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
        self.influx_org = os.getenv("INFLUX_ORG", "laboratorio")
        self.influx_bucket = os.getenv("INFLUX_BUCKET", "iot_data")
        self.influx_client = InfluxDBClient(url=self.influx_url, token=self.influx_token, org=self.influx_org)

        # 3. Setup MQTT
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
        self.mqtt_port = 1883

    def _log_action(self, action: str, payload: dict, source: str = "agent"):
        """Salva un log per l'auditability"""
        entry = {
            "timestamp": int(time.time()),
            "action": action,
            "payload": payload,
            "source": source
        }
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ==========================================
    # ️ FUNZIONI PER L'OBSERVER MCP (Read-Only)
    # ==========================================

    def get_drones_status(self) -> dict:
        """Legge da Kubernetes lo stato attuale dei droni"""
        try:
            pods = self.k8s_core.list_namespaced_pod(namespace="default", label_selector="app=drone-simulator")
            running_pods = [p.metadata.name for p in pods.items if p.status.phase == "Running"]
            return {
                "total_active_drones": len(running_pods),
                "drone_names": running_pods,
                "max_allowed_without_approval": POLICY_LIMITS["max_drones_auto"]
            }
        except Exception as e:
            return {"error": str(e)}

    def get_drones_telemetry(self, minutes_ago: int = 5) -> dict:
        """Interroga InfluxDB per lo stato dei droni recenti"""
        try:
            query_api = self.influx_client.query_api()
            query = f'''
                from(bucket:"{self.influx_bucket}")
                |> range(start: -{minutes_ago}m)
                |> filter(fn: (r) => r._measurement == "drone_telemetry")
                |> last()
            '''
            tables = query_api.query(query, org=self.influx_org)
            
            results = {}
            print(f"MCP Influx: Query returned {len(tables)} tables")
            for table in tables:
                for record in table.records:
                    values = getattr(record, "values", {}) or {}
                    if not isinstance(values, dict):
                        try:
                            values = dict(values)
                        except Exception:
                            values = {}

                    drone_id = values.get("drone_id", "unknown")
                    field = values.get("_field")
                    value = values.get("_value")

                    
                    drone_entry = results.setdefault(drone_id, {"state": "unknown", "battery": 0, "wear": 0})
                 
                    if field == "status":
                        drone_entry["state"] = value
                    elif field == "battery":
                        drone_entry["battery"] = value
                    elif field == "wear":
                        drone_entry["wear"] = value
            
            # Conta droni in manutenzione
            maintenance_count = sum(1 for d in results.values() if d["state"] == "MAINTENANCE")
            
            return {
                "time_window_minutes": minutes_ago,
                "drones_status": results,
                "maintenance_count": maintenance_count,
                "status": "warning" if maintenance_count > 0 else "ok"
            }
        except Exception as e:
            return {"error": str(e)}

    def get_pending_orders(self, minutes_ago: int = 60) -> dict:
        """Interroga InfluxDB per gli ordini in sospeso"""
        try:
            query_api = self.influx_client.query_api()
       
            query = f'''
                from(bucket:"{self.influx_bucket}")
                |> range(start: -{minutes_ago}m)
                |> filter(fn: (r) => r._measurement == "business_orders")
            '''
            tables = query_api.query(query, org=self.influx_org)
            
            orders = []
            print(f"MCP Influx: Pending orders query returned {len(tables)} tables")
            for table in tables:
                print(f"MCP Influx: Orders table has {len(table.records)} records")
                for record in table.records:
                    values = getattr(record, "values", {}) or {}
                    if not isinstance(values, dict):
                        try:
                            values = dict(values)
                        except Exception:
                            values = {}

                    order_id = values.get("order_id", "unknown")
                    priority = values.get("priority", "normal")
                    weight = values.get("_value")
                    
                    if not any(o["order_id"] == order_id for o in orders):
                        orders.append({
                            "order_id": order_id,
                            "priority": priority,
                            "weight_kg": weight or 0.0,
                            "timestamp": values.get("_time", int(time.time()))
                        })
                    print(f"MCP Influx: Order {order_id} (priority {priority}, weight {weight}kg)")
            
            return {
                "total_pending": len(orders),
                "orders": orders,
                "status": "ok" if orders else "no_pending_orders"
            }
        except Exception as e:
            return {"error": str(e), "total_pending": 0, "orders": []}

    def send_mqtt_command(self, target: str, action: str, force: bool = False, **kwargs) -> dict:
        """Invia un comando MQTT ai droni"""
        # Controllo Policy
        if not force and action in POLICY_LIMITS["requires_human_approval"]:
            return {
                "allowed": False, 
                "reason": f"Il comando {action} è distruttivo. Usa 'request_human_approval'."
            }

        # Esecuzione
        topic = f"comandi/{target}" if target != "all" else "comandi/tutti"
        payload = json.dumps({"action": action, **kwargs})
        try:
            client_mqtt = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"agent-action-{int(time.time())}")
            client_mqtt.connect(self.mqtt_broker, self.mqtt_port, 60)
            client_mqtt.loop_start()               # Avvia il thread di rete in background
            msg_info = client_mqtt.publish(topic, payload, qos=1) 
            msg_info.wait_for_publish()            # Ferma il codice finché non viene spedito davvero
            client_mqtt.loop_stop()
            client_mqtt.disconnect()
            
            self._log_action("send_mqtt_command", {"target": target, "action": action, "kwargs": kwargs})
            return {"allowed": True, "status": "success", "message": f"Comando '{action}' inviato a {topic}"}
        except Exception as e:
            return {"allowed": False, "error": str(e)}

    def scale_drone_deployment(self, replicas: int, force: bool = False) -> dict:
        """Modifica le repliche del deployment droni su Kubernetes"""
        # Controllo Policy
        if not force and replicas > POLICY_LIMITS["max_drones_auto"]:
            return {
                "allowed": False,
                "reason": f"Richiesta di {replicas} droni supera il limite di automazione ({POLICY_LIMITS['max_drones_auto']}). Usa 'request_human_approval'."
            }

        # Esecuzione
        try:
            body = {'spec': {'replicas': replicas}}
            self.k8s_apps.patch_namespaced_deployment_scale(
                name="drone-simulator",
                namespace="default",
                body=body
            )
            self._log_action("scale_deployment", {"replicas": replicas})

            if force:
                self._consume_approval_for_replicas(replicas)

            return {"allowed": True, "status": "success", "message": f"Infrastruttura scalata a {replicas} droni"}
        except Exception as e:
            return {"allowed": False, "error": str(e)}

    def _consume_approval_for_replicas(self, replicas: int):
        approvals = []
        if not self.approvals_file.exists():
            return

        try:
            with open(self.approvals_file, "r") as f:
                for line in f:
                    approvals.append(json.loads(line.strip()))
        except Exception:
            return

        changed = False
        for entry in approvals:
            if entry.get("status") == "approved" and not entry.get("consumed", False):
                if entry.get("payload", {}).get("replicas") == replicas:
                    entry["consumed"] = True
                    changed = True
                    break

        if changed:
            try:
                with open(self.approvals_file, "w") as f:
                    for entry in approvals:
                        f.write(json.dumps(entry) + "\n")
            except Exception:
                pass

    def request_human_approval(self, action_type: str, reason: str, payload: dict = None) -> dict:
        """Strumento per chiedere permesso quando bloccato dalle policy"""
        if payload is None:
            payload = {}
        request_id = f"REQ-{int(time.time())}"
        entry = {
            "request_id": request_id,
            "action_type": action_type,
            "payload": payload,
            "reason": reason,
            "status": "pending",
            "consumed": False
        }
        with open(self.approvals_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            
        self._log_action("request_human_approval", entry)
        return {"status": "pending_approval", "request_id": request_id, "message": "Richiesta inviata all'operatore umano."}

    def check_pending_approvals(self, request_id: str = None) -> dict:
        """Controlla se ci sono approvazioni umane pendenti o approvate"""
        if not self.approvals_file.exists():
            return {"pending": [], "approved": []}
        
        pending = []
        approved = []
        try:
            with open(self.approvals_file, "r") as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if request_id and entry.get("request_id") != request_id:
                        continue
                    if entry["status"] == "pending":
                        pending.append(entry)
                    elif entry["status"] == "approved" and not entry.get("consumed", False):
                        approved.append(entry)
        except Exception as e:
            return {"error": str(e)}
        
        result = {"pending": pending, "approved": approved}
        if request_id:
            result["request_id"] = request_id
        return result