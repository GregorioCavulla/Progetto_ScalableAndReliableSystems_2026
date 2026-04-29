import os
from openai import OpenAI

# --- CONFIGURAZIONE GROQ (leggi da env) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def test_groq_connection():
    print(f"--- ⚡ TEST DI CONNESSIONE GROQ ---")
    
    # Inizializzazione client (Groq è compatibile con l'SDK OpenAI)
    client = OpenAI(
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=(GROQ_API_KEY or None)
    )

    try:
        print(f"Invio richiesta al modello {MODEL_NAME}...")
        
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Sei un assistente tecnico per un progetto IoT universitario."
                },
                {
                    "role": "user",
                    "content": "Ciao Groq! Conferma che la connessione funziona e dimmi brevemente cosa pensi dei sistemi MCP."
                }
            ],
            model=MODEL_NAME,
        )

        content = response.choices[0].message.content
        print("\n✅ CONNESSIONE RIUSCITA!")
        print("-" * 30)
        print(f"Risposta da Groq:\n{content}")
        print("-" * 30)
        
        # Statistiche di utilizzo (fondamentali per il tuo report sui costi/token)
        print(f"\nUtilizzo token: {response.usage.total_tokens}")

    except Exception as e:
        print("\n❌ ERRORE DI CONNESSIONE!")
        print(f"Dettagli: {str(e)}")

if __name__ == "__main__":
    test_groq_connection()