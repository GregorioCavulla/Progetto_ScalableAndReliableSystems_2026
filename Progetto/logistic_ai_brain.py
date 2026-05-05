import os
import time
import json
from openai import OpenAI

# --- CONFIGURAZIONE LLM (OpenAI Compatible via LiteLLM) ---
# Info della tua configurazione
API_BASE = "https://litellm-proxy-1013932759942.europe-west8.run.app/v1"
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = "gemini-2.5-pro" # Alternativa: "vertex_ai/mistral-small-2503"

COMPRESS_THRESHOLD = 8000
STREAM_RESPONSE = True
SAVE_HISTORY = True

# --- INIZIALIZZAZIONE CLIENT ---
# Sfruttiamo l'SDK nativo "OpenAI" ma puntando al tuo proxy LiteLLM (gemini)
client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE
)

def run_agent_loop():
    print("🧠 --- AVVIO ORCHESTRATORE AI (VANILLA LLM AGENT) --- 🧠")
    print(f"🔗 Endpoint: {API_BASE} | Modello: {MODEL_NAME}")
    
    # Memoria della conversazione se l'agente deve mantenere del contesto iterativo
    chat_history = [
        {
            "role": "system",
            "content": (
                "Sei l'Agente Logistico di orchestrazione droni. Il tuo obiettivo è analizzare "
                "gli ordini in attesa e assegnarli ai droni liberi. "
                "Agisci sempre invocando le function calls disponibili."
            )
        }
    ]

    while True:
        try:
            print("\n[AI] 🧐 Valutazione stato e attesa nuovi task...")
            
            # --- 1. TODO: Lettura Contesto e Stato (Sensori, DB, Droni) ---
            # Qui inserirai la logica "Domain-First" per leggere da InfluxDB o interrogare l'MCP
            context_data = "Simulazione: 1 drone libero, 1 ordine pending."
            
            chat_history.append({"role": "user", "content": f"Nuovo stato sistema: {context_data}"})
            
            # Trunking opzionale basato su COMPRESS_THRESHOLD (per evitare esplosioni di contesto)
            # if len(str(chat_history)) > COMPRESS_THRESHOLD:
            #     comprimere o pulire la cronologia

            # --- 2. Invocazione del Modello LLM ---
            # response = client.chat.completions.create(
            #     model=MODEL_NAME,
            #     messages=chat_history,
            #     stream=STREAM_RESPONSE,
            #     # tools=[qui_andra_definito_lo_schema_json_dei_tuoi_tool_mcp]
            # )
            
            # --- 3. TODO: Esecuzione Tools (Reason & Act) ---
            # Se l'LLM risponde con `tool_calls`, iteriamo su di essi per assegnare ordini 
            # tramite MQTT o per interrogare altre metriche.
            
            time.sleep(15) # Pausa tra un'orbita decisionale e l'altra

        except Exception as e:
            print(f"❌ Errore nel loop dell'ormatore LLM: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        run_agent_loop()
    except KeyboardInterrupt:
        print("\n🛑 Spegnimento orchestratore...")