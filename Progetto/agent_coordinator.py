import os
import sys
from health_agent import HealthAgent
from logistic_agent import LogisticAgent

# --- CONFIGURAZIONE ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8101")
MCP_TOKEN = os.getenv("MCP_TOKEN", "segreto-universitario")

def main():
    print("==================================================")
    print("   🚀 DRONE AGENTIC SYSTEM - COORDINATOR        ")
    print("==================================================")

    # Inizializzazione Health Agent
    print("\n[1/3] Inizializzazione Health Agent...")
    health_agent = HealthAgent(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        model=MODEL_NAME,
        mcp_url=MCP_SERVER_URL,
        token=MCP_TOKEN
    )

    # Esecuzione monitoraggio salute
    print("[2/3] Monitoraggio salute flotta droni...")
    try:
        health_report = health_agent.run()
        print(f"\n📢 REPORT SALUTE:\n{'-'*30}\n{health_report}\n{'-'*30}")
    except Exception as e:
        print(f"❌ Errore Health Agent: {e}")
        sys.exit(1)

    # Inizializzazione Logistic Agent
    print("\n[3/3] Inizializzazione Logistic Agent...")
    logistic_agent = LogisticAgent(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        model=MODEL_NAME,
        mcp_url=MCP_SERVER_URL,
        token=MCP_TOKEN
    )

    # Per ora, ordini fittizi; in produzione, leggere da InfluxDB
    orders_queue = [
        {"order_id": "ORD-123", "pickup_lat": 0.01, "pickup_lon": 0.01, "drop_lat": 0.02, "drop_lon": 0.02}
    ]

    print("Gestione ordini di consegna...")
    try:
        logistic_report = logistic_agent.run(orders_queue)
        print(f"\n✅ REPORT LOGISTICO:\n{'-'*30}\n{logistic_report}\n{'-'*30}")
    except Exception as e:
        print(f"❌ Errore Logistic Agent: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("        SISTEMA OPERATIVO                         ")
    print("==================================================")

if __name__ == "__main__":
    if not GROQ_API_KEY:
        print("❌ ERRORE: Inserisci GROQ_API_KEY.")
    else:
        main()