import os
import sys
import json
import requests
from pydantic import BaseModel, Field
from pydantic.v1 import BaseModel as BaseModelV1
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

# --- CONFIGURAZIONE GROQ & INFRASTRUTTURA ---
GROQ_API_KEY = os.getenv("chiave_groq", "chiave_groq")
os.environ["OPENAI_API_KEY"] = GROQ_API_KEY
os.environ["OPENAI_API_BASE"] = "https://api.groq.com/openai/v1"
MODEL_NAME = "openai/llama-3.3-70b-versatile"

OBSERVER_SERVER_URL = "http://localhost:8101" #q: a che file corrisponde? --- a: MCP Observer Server, in che file si trova? --- a: MCP Observer Server, in mcp_server.py
OPERATIONS_SERVER_URL = "http://localhost:8102"  #q: a che file corrisponde? --- a: MCP Operations Server, in che file si trova? --- a: MCP Operations Server, in mcp_server.py
OPERATIONS_TOKEN = "segreto-universitario"

# Definizione dei Tool per l'Observer
@tool("get_cluster_status")
def get_cluster_status() -> str:
    """Ottieni lo stato dei sensori attivi su Kubernetes."""
    try:
        resp = requests.post(f"{OBSERVER_SERVER_URL}/tool", json={"name": "get_cluster_status", "args": {}}, timeout=5)
        return json.dumps(resp.json().get("result", {}))
    except Exception as e:
        return f"Errore observer: {e}"

@tool("get_telemetry_summary")
def get_telemetry_summary(minutes_ago: int = 5) -> str:
    """Ottieni la media delle temperature recenti da InfluxDB."""
    try:
        resp = requests.post(f"{OBSERVER_SERVER_URL}/tool", json={"name": "get_telemetry_summary", "args": {"minutes_ago": minutes_ago}}, timeout=5)
        return json.dumps(resp.json().get("result", {}))
    except Exception as e:
        return f"Errore observer: {e}"

# Definizione dei Tool per il Remediation
@tool("send_mqtt_command")
def send_mqtt_command(target: str, command: str) -> str:
    """Invia un comando MQTT a un sensore smart."""
    try:
        headers = {"X-MCP-Token": OPERATIONS_TOKEN}
        resp = requests.post(f"{OPERATIONS_SERVER_URL}/tool", json={"name": "send_mqtt_command", "args": {"target": target, "command": command}}, headers=headers, timeout=5)
        return json.dumps(resp.json().get("result", {}))
    except Exception as e:
        return f"Errore ops: {e}"

@tool("scale_sensor_deployment")
def scale_sensor_deployment(replicas: int) -> str:
    """Scala il numero di pod dei sensori su Kubernetes."""
    try:
        headers = {"X-MCP-Token": OPERATIONS_TOKEN}
        resp = requests.post(f"{OPERATIONS_SERVER_URL}/tool", json={"name": "scale_sensor_deployment", "args": {"replicas": replicas}}, headers=headers, timeout=5)
        return json.dumps(resp.json().get("result", {}))
    except Exception as e:
        return f"Errore ops: {e}"

@tool("request_human_approval")
def request_human_approval(action_type: str, reason: str) -> str:
    """Chiedi autorizzazione per azioni ad alto impatto."""
    try:
        headers = {"X-MCP-Token": OPERATIONS_TOKEN}
        resp = requests.post(f"{OPERATIONS_SERVER_URL}/tool", json={"name": "request_human_approval", "args": {"action_type": action_type, "reason": reason}}, headers=headers, timeout=5)
        return json.dumps(resp.json().get("result", {}))
    except Exception as e:
        return f"Errore ops: {e}"


def main():
    print("==================================================")
    print("   🚀 IOT AGENTIC SYSTEM - COORDINATOR (CREWAI)  ")
    print("==================================================")

    # 1. Definizione dell'Agente Observer
    observer_agent = Agent(
        role="Observer Agent",
        goal="Ispezionare la telemetria e lo stato del cluster Kubernetes. Identificare anomalie e generare un triage",
        backstory=(
            "Sei un sistema esperto progettato per monitorare infrastrutture IoT "
            "e individuare anomalie come spike di temperatura o pod mancanti. "
            "Non tenti mai di agire sul sistema, solo osservare ed evidenziare i problemi."
        ),
        tools=[get_cluster_status, get_telemetry_summary],
        llm=MODEL_NAME,
        verbose=True
    )

    # 2. Definizione dell'Agente Remediation
    remediation_agent = Agent(
        role="Remediation Agent",
        goal="Ricevere il triage dall'osservatore e intraprendere azioni per mettere in sicurezza il sistema",
        backstory=(
            "Sei un ingegnere esperto di affidabilità (SRE). Il tuo compito è risolvere i problemi "
            "segnalati senza fare danni. Segui strettamente le regole: se scali oltre 6 repliche o "
            "vuoi spegnere istanze, chiedi l'approvazione umana. Altrimenti, esegui i comandi MQTT o scala i pod."
        ),
        tools=[send_mqtt_command, scale_sensor_deployment, request_human_approval],
        llm=MODEL_NAME,
        verbose=True
    )

    # 3. Definizione dei Task
    monitor_task = Task(
        description="Esegui un controllo di routine della telemetria (ultimi 1 min) e dello stato del cluster Kubernetes per identificare sensori problematici o pod inattivi. Formula una chiara diagnosi (triage).",
        expected_output="Un report dettagliato sugli attuali sensori attivi, le loro temperature medie, e in caso di anomalie, le priorità di intervento.",
        agent=observer_agent
    )

    resolve_task = Task(
        description="Ricevi il triage in ingresso e agisci sulle anomalie. Se la temperatura è alta nei sensori smart, invia comandi per accendere le ventole. Se i pod sono in numero insufficiente, scalali dinamicamente. Restituisci cosa hai eseguito.",
        expected_output="Il riepilogo delle azioni intraprese per riparare il sistema in risposta alle problematiche rilevate.",
        agent=remediation_agent
    )

    # 4. Assegnazione della Squadra (Crew)
    iot_crew = Crew(
        agents=[observer_agent, remediation_agent],
        tasks=[monitor_task, resolve_task],
        process=Process.sequential,
        verbose=True
    )

    print("\n[Inizio operazioni della Crew...]")
    try:
        # Avvia l'esecuzione
        risultato = iot_crew.kickoff()
        
        print("\n✅ RISULTATO FINALE DELLA CREW:")
        print("-" * 40)
        print(risultato)
        print("-" * 40)
        
    except Exception as e:
        print(f"❌ Errore durante le operazioni della Crew: {e}")

if __name__ == "__main__":
    main()
