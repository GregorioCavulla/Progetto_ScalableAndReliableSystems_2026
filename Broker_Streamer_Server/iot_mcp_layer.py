#!/usr/bin/env python3

import os
import json
import time
from pathlib import Path
from kubernetes import client, config
from influxdb_client import InfluxDBClient
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Costanti e Policy di Sicurezza (Guardrails)
POLICY_LIMITS = {
    "max_replicas_auto": 6, # Oltre 6 pod l'agente deve chiedere il permesso all'umano
    "requires_human_approval": ["SPEGNI_TUTTO", "REBOOT_SISTEMA", "AGGIORNAMENTO_FIRMWARE"],
    "cost_per_pod_eur": 0.02 # Costo fittizio per calcolare il budget
}

class IotMCP:
    def __init__(self, data_dir="data"):
        # Setup cartella per i log di audit e approvazioni (richiesto dal progetto)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.data_dir / "audit_actions.jsonl"
        self.approvals_file = self.data_dir / "pending_approvals.jsonl"

        # 1. Setup Kubernetes
        try:
            config.load_incluster_config() # Prova a caricare config interna al Pod
        except:
            try:
                config.load_kube_config() # Fallback: usa config locale per test dal tuo PC
            except Exception as e:
                print(f"⚠️ Avviso K8s: Impossibile caricare configurazione ({e})")
        
        self.k8s_apps = client.AppsV1Api()
        self.k8s_core = client.CoreV1Api()

        # 2. Setup InfluxDB (Stesse variabili del server_centrale)
        self.influx_url = os.getenv("INFLUX_URL", "http://localhost:8086") # Usa localhost se testi da PC
        self.influx_token = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
        self.influx_org = os.getenv("INFLUX_ORG", "laboratorio")
        self.influx_bucket = os.getenv("INFLUX_BUCKET", "iot_data")
        self.influx_client = InfluxDBClient(url=self.influx_url, token=self.influx_token, org=self.influx_org)

        # 3. Setup MQTT
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost") # Usa localhost se testi da PC
        self.mqtt_port = 1883

    def _log_action(self, action: str, payload: dict, source: str = "agent"):
        """Salva un log per l'auditability (Requisito di progetto)"""
        entry = {
            "timestamp": int(time.time()),
            "action": action,
            "payload": payload,
            "source": source
        }
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ==========================================
    # 👁️ FUNZIONI PER L'OBSERVER MCP (Read-Only)
    # ==========================================

    def get_cluster_status(self) -> dict:
        """Legge da Kubernetes lo stato attuale dei sensori"""
        try:
            pods = self.k8s_core.list_namespaced_pod(namespace="default", label_selector="app=sensore-b")
            running_pods = [p.metadata.name for p in pods.items if p.status.phase == "Running"]
            return {
                "total_active_sensors": len(running_pods),
                "sensor_names": running_pods,
                "max_allowed_without_approval": POLICY_LIMITS["max_replicas_auto"]
            }
        except Exception as e:
            return {"error": str(e)}

    def get_telemetry_summary(self, minutes_ago: int = 5) -> dict:
        """Interroga InfluxDB per calcolare media/max/min delle temperature recenti"""
        try:
            query_api = self.influx_client.query_api()
            # Query Flux per calcolare la media degli ultimi X minuti
            query = f'''
                from(bucket:"{self.influx_bucket}")
                |> range(start: -{minutes_ago}m)
                |> filter(fn: (r) => r._measurement == "ambiente" and r._field == "valore")
                |> mean()
            '''
            tables = query_api.query(query, org=self.influx_org)
            
            results = {}
            for table in tables:
                for record in table.records:
                    sensore = record.values.get("sensore", "unknown")
                    valore_medio = record.get_value()
                    results[sensore] = round(valore_medio, 2)
            
            return {
                "time_window_minutes": minutes_ago,
                "average_temperatures": results,
                "status": "warning" if any(v > 28.0 for v in results.values()) else "ok"
            }
        except Exception as e:
            return {"error": str(e)}

    # ==========================================
    # 🛠️ FUNZIONI PER L'ACTION MCP (Write)
    # ==========================================

    def send_mqtt_command(self, target: str, command: str) -> dict:
        """Invia un comando MQTT (con blocco sicurezza per azioni critiche)"""
        # 1. Controllo Policy (Guardrail)
        if command in POLICY_LIMITS["requires_human_approval"]:
            return {
                "allowed": False, 
                "reason": f"Il comando {command} è distruttivo. Usa 'request_human_approval'."
            }

        # 2. Esecuzione
        topic = f"comandi/{target}" if target != "tutti" else "comandi/tutti"
        try:
            client_mqtt = mqtt.Client(CallbackAPIVersion.VERSION2, "agent-action")
            client_mqtt.connect(self.mqtt_broker, self.mqtt_port, 60)
            client_mqtt.publish(topic, command)
            client_mqtt.disconnect()
            
            self._log_action("send_mqtt_command", {"target": target, "command": command})
            return {"allowed": True, "status": "success", "message": f"Comando '{command}' inviato a {topic}"}
        except Exception as e:
            return {"allowed": False, "error": str(e)}

    def scale_sensor_deployment(self, replicas: int) -> dict:
        """Modifica le repliche su Kubernetes (con blocco economico/quantitativo)"""
        # 1. Controllo Policy (Guardrail Economico/Quantitativo)
        if replicas > POLICY_LIMITS["max_replicas_auto"]:
            return {
                "allowed": False,
                "reason": f"Richiesta di {replicas} pod supera il limite di automazione ({POLICY_LIMITS['max_replicas_auto']}). Usa 'request_human_approval'."
            }

        # 2. Esecuzione
        try:
            body = {'spec': {'replicas': replicas}}
            self.k8s_apps.patch_namespaced_deployment_scale(
                name="app-sensore-b",
                namespace="default",
                body=body
            )
            self._log_action("scale_deployment", {"replicas": replicas})
            return {"allowed": True, "status": "success", "message": f"Infrastruttura scalata a {replicas} sensori"}
        except Exception as e:
            return {"allowed": False, "error": str(e)}

    def request_human_approval(self, action_type: str, payload: dict, reason: str) -> dict:
        """Strumento per l'Agente per chiedere permesso quando bloccato dalle policy"""
        request_id = f"REQ-{int(time.time())}"
        entry = {
            "request_id": request_id,
            "action_type": action_type,
            "payload": payload,
            "reason": reason,
            "status": "pending"
        }
        with open(self.approvals_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            
        self._log_action("request_human_approval", entry)
        return {"status": "pending_approval", "request_id": request_id, "message": "Richiesta inviata all'operatore umano."}