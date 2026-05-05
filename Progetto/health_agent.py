import os
import json
import requests
from openai import OpenAI

# Prompt di sistema per l'Health Agent
SYSTEM_PROMPT = (
    "Sei l'HealthAgent del sistema di droni. Il tuo compito è monitorare la salute della flotta di droni. "
    "Puoi leggere lo stato dei droni e la loro telemetria da InfluxDB. "
    "Se rilevi droni in stato MAINTENANCE (batteria == 0 o usura elevata), "
    "devi scalare il numero di droni aggiungendone di nuovi per mantenere la flotta operativa. "
    "Usa i tool disponibili per leggere dati e scalare l'infrastruttura. "
    "Se devi scalare oltre il limite automatico, chiedi approvazione umana."
)

class HealthAgent:
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
                    "name": "scale_drone_deployment",
                    "description": "Scala il numero di droni su Kubernetes.",
                    "parameters": {
                        "type": "object",
                        "properties": {"replicas": {"type": "integer"}},
                        "required": ["replicas"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_human_approval",
                    "description": "Chiedi autorizzazione per azioni ad alto impatto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action_type": {"type": "string"},
                            "reason": {"type": "string"}
                        }
                    }
                }
            }
        ]

    def call_mcp(self, name, args):
        """Chiamata al server MCP con Token"""
        headers = {"X-MCP-Token": self.token}
        resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers)
        return resp.json().get("result", {})

    def run(self):
        print("Health Agent: Starting run")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Controlla la salute della flotta di droni e prendi azioni correttive se necessario."}
        ]

        try:
            # Ciclo di ragionamento dell'LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools
            )
        except Exception as e:
            print(f"Health Agent: Error calling LLM: {e}")
            return f"Errore LLM: {e}"

        msg = response.choices[0].message
        print(f"Health Agent: Received response, tool_calls: {len(msg.tool_calls) if msg.tool_calls else 0}")
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