import os
import json
import requests
from openai import OpenAI

# Prompt di sistema per il Logistic Agent
SYSTEM_PROMPT = (
    "Sei il LogisticAgent del sistema di droni. Il tuo compito è gestire gli ordini di consegna con ragionamenti complessi. "
    "Leggi la coda ordini, lo stato dei droni e la loro telemetria. "
    "Valuta la priorità degli ordini e lo stato dei droni (batteria, usura). "
    "Se ci sono ordini ad alta priorità e droni con usura elevata (es. 60%), fai un ragionamento probabilistico per determinare quale missione sia meno rischiosa, valutando il trade-off tra priorità e rischio di fallimento. "
    "Scegli il drone più adatto considerando distanza, stato e probabilità di successo. "
    "Invia un comando MQTT al drone selezionato per assegnare la missione. "
    "Usa i tool disponibili per leggere dati e inviare comandi."
)

# TODO: valutare il guadagno in base a incasso ordine - wear e batteria drone (costi stimati per ogni missione) e usarlo come metrica per decidere le assegnazioni

# TODO: pulire il log

class LogisticAgent:
    def __init__(self, api_key, base_url, model, mcp_url, token):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        
        # Definizione dei tool MCP
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_drones_status",
                    "description": "Ottieni lo stato dei droni attivi su Kubernetes.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_drones_telemetry",
                    "description": "Ottieni la telemetria recente dei droni da InfluxDB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes_ago": {"type": "integer", "default": 5}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pending_orders",
                    "description": "Ottieni gli ordini in sospeso da InfluxDB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes_ago": {"type": "integer", "default": 60}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_mqtt_command",
                    "description": "Invia un comando MQTT a un drone per assegnare una missione.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "action": {"type": "string"},
                            "order_id": {"type": "string"},
                            "target_lat": {"type": "number"},
                            "target_lon": {"type": "number"}
                        },
                        "required": ["target", "action"]
                    }
                }
            }
        ]

    def call_mcp(self, name, args):
        """Chiamata al server MCP con Token"""
        headers = {"X-MCP-Token": self.token}
        try:
            resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers, timeout=15)
            
            # Se la risposta non è un JSON valido (es. Flask ha restituito un errore 500 HTML)
            try:
                return resp.json().get("result", {})
            except requests.exceptions.JSONDecodeError:
                return {"error": f"Errore interno del server MCP. Risposta non JSON: HTTP {resp.status_code}"}
                
        except requests.exceptions.RequestException as e:
            # Cattura problemi di rete, timeout, o server irraggiungibile
            return {"error": f"Errore di rete o timeout contattando l'MCP: {str(e)}"}

    def run(self, orders_queue=None):
        print("\n LOGISTIC AGENT - GESTIONE ORDINI")
        
        # Se orders_queue non è fornito, istruiamo l'LLM a recuperarlo
        if orders_queue is None or len(orders_queue) == 0:
            user_message = "Leggi gli ordini in sospeso dal sistema e assegna i droni disponibili alle missioni. Usa il tool get_pending_orders per recuperare gli ordini da InfluxDB."
        else:
            user_message = f"Gestisci questi ordini: {json.dumps(orders_queue)}"
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        print(" Ragionamento in corso...")
        
        # QUESTO È IL CUORE DELL'AGENTE: Un loop che continua finché l'LLM non ha finito
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools
                )
                
                msg = response.choices[0].message
                
                # 1. CONDIZIONE DI USCITA: Se l'LLM NON vuole usare tool, ha finito il ragionamento
                if not msg.tool_calls:
                    final_content = msg.content
                    if final_content is None:
                        final_content = "Elaborazione completata (Azione eseguita senza commenti testuali)."
                    
                    print(f" Rapporto Finale: {final_content}")
                    return final_content
                
                # 2. ESECUZIONE TOOL: L'LLM vuole raccogliere altri dati o eseguire azioni
                tool_count = len(msg.tool_calls)
                print(f" Uso {tool_count} tool per raccogliere dati...")
                
                # Salviamo l'intenzione dell'LLM nella cronologia
                messages.append(msg)
                
                # Eseguiamo tutti i tool che ha richiesto
                for i, tool_call in enumerate(msg.tool_calls, 1):
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    # Chiama il server MCP
                    result = self.call_mcp(tool_name, tool_args)
                    
                    # Salviamo il risultato del tool nella cronologia
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(result)
                    })
                
                print(" Continuo ragionamento con nuovi dati...")
                # Il ciclo riparte! Ora l'LLM vedrà i dati e deciderà il prossimo tool da usare.
                
            except Exception as e:
                print(f" Errore: {e}")
                return f"Errore: {e}"