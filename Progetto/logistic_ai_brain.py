import os
import time
import json
import sys
sys.stdout.reconfigure(line_buffering=True)
from openai import OpenAI
from health_agent import HealthAgent
from logistic_agent import LogisticAgent

# --- CONFIGURAZIONE LLM ---
API_BASE = "https://litellm-proxy-1013932759942.europe-west8.run.app/v1"
API_KEY = os.getenv("OPENAI_API_KEY", "sk-BI1ty8WHJ-PBrVP5_ElhZA")
MODEL_NAME = "gemini-2.5-pro"

# MCP Config
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8101")
MCP_TOKEN = os.getenv("MCP_TOKEN", "REDACTED_MCP_TOKEN")

# Inizializzazione agenti
health_agent = HealthAgent(
    api_key=API_KEY,
    base_url=API_BASE,
    model=MODEL_NAME,
    mcp_url=MCP_SERVER_URL,
    token=MCP_TOKEN
)

logistic_agent = LogisticAgent(
    api_key=API_KEY,
    base_url=API_BASE,
    model=MODEL_NAME,
    mcp_url=MCP_SERVER_URL,
    token=MCP_TOKEN
)

# TODO: pulire il log

def run_agent_loop():
    print(" --- AVVIO ORCHESTRATORE AI (VANILLA LLM AGENT) --- ")
    
    if not API_KEY:
        print(" OPENAI_API_KEY non settata! Imposta la variabile d'ambiente.")
        return
    
    while True:
        try:
            # Esecuzione Health Agent
            try:
                health_report = health_agent.run()
                print(f" Salute Flotta: {health_report}")
            except Exception as e:
                print(f" Errore Health Agent: {e}")
            
            # Gestione ordini - l'agente leggerà da InfluxDB via tool get_pending_orders
            try:
                logistic_report = logistic_agent.run()
                print(f" Logistica: {logistic_report}")
            except Exception as e:
                print(f" Errore Logistic Agent: {e}")
            
            time.sleep(30)  # Pausa tra cicli

        except Exception as e:
            print(f" Errore nel loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        run_agent_loop()
    except KeyboardInterrupt:
        print("\n Spegnimento orchestratore...")