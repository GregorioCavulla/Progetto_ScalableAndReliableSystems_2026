import os
import json
import requests
from openai import OpenAI

# Prompt di sistema per il Logistic Agent
SYSTEM_PROMPT = (
    "Sei il LogisticAgent del sistema di droni. Il tuo compito è gestire gli ordini di consegna. "
    "Leggi la coda ordini e la telemetria dei droni. "
    "Scegli un drone in stato IDLE più vicino o adatto all'ordine. "
    "Invia un comando MQTT al drone selezionato per assegnare la missione. "
    "Usa i tool disponibili per leggere dati e inviare comandi."
)

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
        resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers)
        return resp.json().get("result", {})

    def run(self, orders_queue):
        print("Logistic Agent: Starting run")
        # Per semplicità, assumiamo che orders_queue sia una lista di ordini
        # In produzione, leggere da InfluxDB o MQTT
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Gestisci questi ordini: {json.dumps(orders_queue)}"}
        ]

        try:
            # Ciclo di ragionamento
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools
            )
        except Exception as e:
            print(f"Logistic Agent: Error calling LLM: {e}")
            return f"Errore LLM: {e}"

        msg = response.choices[0].message
        print(f"Logistic Agent: Received response, tool_calls: {len(msg.tool_calls) if msg.tool_calls else 0}")
        if msg.tool_calls:
            # 1. APPEND FUORI DAL CICLO: Aggiungiamo l'intenzione dell'IA UNA SOLA VOLTA
            messages.append(msg)
            
            # 2. CICLO SUI TOOL: Eseguiamo ogni tool richiesto
            for tool_call in msg.tool_calls:
                # Per i log, aggiungiamo il prefisso del file in cui ti trovi
                print(f"Calling tool {tool_call.function.name}")
                result = self.call_mcp(tool_call.function.name, json.loads(tool_call.function.arguments))
                print(f"Tool result: {result}")
                
                # 3. APPEND DEL RISULTATO DENTRO IL CICLO
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(result)
                })
            
            try:
                # 4. CHIAMATA FINALE A GEMINI
                final_resp = self.client.chat.completions.create(model=self.model, messages=messages)
                
                # --- FIX PER IL BUG "NoneType" ---
                final_content = final_resp.choices[0].message.content
                if final_content is None:
                    final_content = "Elaborazione completata con successo (Nessun output testuale aggiuntivo)."
                
                print(f"Final response: {final_content[:100]}...")
                return final_content
                
            except Exception as e:
                print(f"Error in final response: {e}")
                return f"Errore finale: {e}"
                
        # Se non ci sono tool chiamati, restituisce il contenuto normale
        return msg.content or "Nessun output generato."