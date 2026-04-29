import os
from openai import OpenAI

# --- CONFIGURAZIONE CREDENZIALI (leggi da environment) ---
API_KEY = os.getenv("TEST_API_KEY", "")
BASE_URL = os.getenv("TEST_BASE_URL", "")
MODEL_NAME = os.getenv("TEST_MODEL_NAME", "")

def test_university_connection():
    print(f"--- TEST DI CONNESSIONE LITELLM ---")
    print(f"Modello: {MODEL_NAME or '<non impostato>'}")
    print(f"Endpoint: {BASE_URL or '<non impostato>'}")
    
    # Inizializzazione del client compatibile con OpenAI
    client = OpenAI(
        api_key=(API_KEY or None),
        base_url=(BASE_URL or None)
    )

    try:
        print("\nInvio richiesta di test...")
        
        # Test semplice: chiediamo al modello di identificarsi
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Sei un assistente per un progetto di sistemi distribuiti."},
                {"role": "user", "content": "Ciao! Conferma la tua identità e che la connessione funziona."}
            ],
            temperature=0.7
        )

        # Stampa del risultato
        content = response.choices[0].message.content
        print("\n✅ CONNESSIONE RIUSCITA!")
        print("-" * 30)
        print(f"Risposta dal modello:\n{content}")
        print("-" * 30)
        
        # Nota sul consumo (Utile per il report ROI del progetto)
        print(f"\nUtilizzo token: {response.usage.total_tokens} (Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens})")

    except Exception as e:
        print("\n❌ ERRORE DI CONNESSIONE!")
        print(f"Dettagli errore: {str(e)}")
        print("\nControlla che l'API_KEY e il BASE_URL siano corretti e che il modello sia attivo.")

if __name__ == "__main__":
    test_university_connection()