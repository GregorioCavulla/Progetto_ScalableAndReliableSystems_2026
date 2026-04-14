import os
from openai import OpenAI

# --- CONFIGURAZIONE CREDENZIALI UNIVERSITARIE ---
# Inserisci qui i dati che ti sono stati forniti
API_KEY = "sk-mtsNMWqdXaQ_YZFeEMIBfA"      # Sostituisci con la tua API Key
BASE_URL = "https://litellm-proxy-1013932759942.europe-west8.run.app"    # Sostituisci con l'URL base (es. https://.../v1)
MODEL_NAME = "vertex_ai/mistral-small-2503"     # Sostituisci con il nome modello (es. gemini/gemini-1.5-pro)

def test_university_connection():
    print(f"--- TEST DI CONNESSIONE LITELLM ---")
    print(f"Modello: {MODEL_NAME}")
    print(f"Endpoint: {BASE_URL}")
    
    # Inizializzazione del client compatibile con OpenAI
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL
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