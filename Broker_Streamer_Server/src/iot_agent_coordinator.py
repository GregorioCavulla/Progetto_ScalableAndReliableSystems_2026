import os
import sys
# Importiamo le classi dai file che hai creato
from observer_agent import ObserverAgent
from remediation_agent import RemediationAgent

# --- CONFIGURAZIONE GROQ & INFRASTRUTTURA ---
# Leggi le chiavi e gli endpoint da environment per sicurezza
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
# Modello Llama 3.3 su Groq (default)
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")

# Endpoint dei server MCP (Assicurati che siano attivi)
OBSERVER_SERVER_URL = os.getenv("OBSERVER_SERVER_URL", "http://mcp-observer-service:8101")
OPERATIONS_SERVER_URL = os.getenv("OPERATIONS_SERVER_URL", "http://mcp-operations-service:8102")
OPERATIONS_TOKEN = os.getenv("OPERATIONS_TOKEN", "segreto-universitario")

def main():
    print("==================================================")
    print("   🚀 IOT AGENTIC SYSTEM - COORDINATOR (GROQ)    ")
    print("==================================================")

    # 1. Inizializzazione dell'Observer Agent
    print("\n[1/3] Inizializzazione Observer Agent...")
    observer = ObserverAgent(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        model=MODEL_NAME,
        obs_url=OBSERVER_SERVER_URL
    )

    # 2. Esecuzione Monitoraggio e Diagnosi
    print("[2/3] Fase di Osservazione: Analisi telemetria e cluster...")
    try:
        diagnosi = observer.run()
        print(f"\n📢 REPORT DI DIAGNOSI:\n{'-'*30}\n{diagnosi}\n{'-'*30}")
    except Exception as e:
        print(f"❌ Errore durante l'osservazione: {e}")
        sys.exit(1)

    # 3. Inizializzazione e Esecuzione del Remediation Agent
    print("\n[3/3] Inizializzazione Remediation Agent...")
    remediator = RemediationAgent(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        model=MODEL_NAME,
        ops_url=OPERATIONS_SERVER_URL,
        token=OPERATIONS_TOKEN
    )

    print("Esecuzione Azioni Correttive basate sulla diagnosi...")
    try:
        risultato_azione = remediator.run(diagnosi)
        print(f"\n✅ RISULTATO OPERAZIONI:\n{'-'*30}\n{risultato_azione}\n{'-'*30}")
    except Exception as e:
        print(f"❌ Errore durante la remediation: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("        SISTEMA IN STATO DI SICUREZZA             ")
    print("==================================================")

if __name__ == "__main__":
    # Verifica che la chiave sia stata inserita
    if not GROQ_API_KEY:
        print("❌ ERRORE: Inserisci la tua API KEY di Groq nella variabile d'ambiente GROQ_API_KEY.")
    else:
        main()