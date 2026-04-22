import os
import json
import requests
from openai import OpenAI

# --- CONFIGURAZIONE --
# Inseriamo la API KEY di default (sostituiscila con la tua o usa le d'ambiente)
<<<<<<< HEAD
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "chiave_groq")
=======
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
>>>>>>> parent of e51111b (ProvineLab0)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL_NAME = "llama-3.3-70b-versatile"

OBSERVER_URL = "http://mcp-observer-service:8101/tool"
OPERATIONS_URL = "http://mcp-operations-service:8102/tool"
TOKEN = "segreto-universitario"

SYSTEM_PROMPT = """Sei l'Assistente AI del Pannello di Controllo IoT.
Il tuo compito è aiutare l'operatore umano a gestire il cluster di droni/sensori.
Usa i tool a disposizione per eseguire i comandi.
Rispondi in modo conciso, descrivendo l'azione effettuata."""

# Tool configurati per fare da ponte al Server MCP
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_cluster_status",
            "description": "Ottieni lo stato dei pod (quanti ce ne sono attivi e i loro nomi).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_telemetry_summary",
            "description": "Controlla la telemetria media recente e lo stato del cluster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes_ago": {"type": "integer", "description": "Minuti passati da analizzare (default 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_mqtt_command",
            "description": "Invia un comando MQTT (es. 'ACCENDI_VENTOLA', 'SPEGNI_VENTOLA') a un target specifico oppure al target 'tutti'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Nome del target del pod (es: sensore-b-xyz) o 'tutti'"},
                    "command": {"type": "string", "description": "Il comando da inviare al target"}
                },
                "required": ["target", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scale_sensor_deployment",
            "description": "Cambia il numero di repliche del deployment app-sensore-b per scalare l'infrastruttura.",
            "parameters": {
                "type": "object",
                "properties": {
                    "replicas": {"type": "integer", "description": "Il numero di repliche desiderate (pod)"}
                },
                "required": ["replicas"]
            }
        }
    }
]

def chiama_mcp(name, args):
    """Chiama il server MCP corretto a seconda del comando"""
    headers = {"X-MCP-Token": TOKEN}
    
    # Smistamento Read vs Write
    if name in ["get_cluster_status", "get_telemetry_summary"]:
        url = OBSERVER_URL
    else:
        url = OPERATIONS_URL
        
    try:
        resp = requests.post(url, json={"name": name, "args": args}, headers=headers, timeout=5)
        return resp.json().get("result", {})
    except requests.exceptions.RequestException as e:
        return {"error": f"Errore di connessione a {url}: {e}"}

def interpella_agente(client, history):
    print("\n⏳ [L'Agente sta elaborando la richiesta...]")
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=history,
        tools=TOOLS
    )
    
    msg = response.choices[0].message
    
    while msg.tool_calls:
        for tool_call in msg.tool_calls:
            print(f"🛠️ [TOOL] L'Agente ha deciso di chiamare: {tool_call.function.name}({tool_call.function.arguments})")
            
            # Esecuzione Tool
            args = json.loads(tool_call.function.arguments)
            risultato = chiama_mcp(tool_call.function.name, args)
            print(f"📡 [RISPOSTA TOOL]: {json.dumps(risultato, indent=2)}")
            
            history.append(msg)
            history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": json.dumps(risultato)
            })
            
        print("\n⏳ [L'Agente sta valutando il risultato e generando la risposta finale...]")
        # Nuovo step di reasoning
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=history,
            tools=TOOLS
        )
        msg = response.choices[0].message
        
    history.append({"role": "assistant", "content": msg.content})
    return msg.content

def avvia_pannello_ai():
    print("==================================================")
    print("   🤖  PANNELLO KUBERNETES IoT - GUIDATO DA GROQ  ")
    print("==================================================")
    
    # Usa le API key per Groq
    if GROQ_API_KEY.startswith("gsk_Fdjy") and GROQ_API_KEY.endswith("CN:"): # dummy check
        print("⚠️ ATTENZIONE: Ricordati di impostare la tua vera API KEY di Groq!")
        
    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    print("Digita i comandi che desideri (es: 'accendi tutte le ventole', 'quanti sensori ci sono attivi?')")
    print("Digita 'esci' o 'exit' per chiudere.")
    
    while True:
        prompt = input("\n👤 Tu: ")
        
        if prompt.lower() in ['esci', 'exit', 'quit', '0']:
            print("👋 Uscita dal Pannello AI.")
            break
            
        if not prompt.strip():
            continue
            
        history.append({"role": "user", "content": prompt})
        
        try:
            risposta = interpella_agente(client, history)
            print("--------------------------------------------------")
            print(f"🤖 Agente: {risposta}")
            print("--------------------------------------------------")
        except Exception as e:
            print(f"\n❌ [ERRORE DI COMUNICAZIONE Groq]: {e}")
            history.pop() # Rimuovi l'ultimo prompt problematico

if __name__ == "__main__":
    avvia_pannello_ai()