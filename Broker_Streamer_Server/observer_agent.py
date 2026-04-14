import os
import json
import requests
from openai import OpenAI

# Prompt di sistema: definisce il ruolo e i limiti dell'agente 
SYSTEM_PROMPT = (
    "Sei l'ObserverAgent del sistema IoT. Il tuo compito è ispezionare la telemetria "
    "e lo stato del cluster Kubernetes. Puoi solo leggere dati. "
    "Se rilevi anomalie (es. temperature > 28°C o pod mancanti), genera un triage "
    "conciso per il RemediationAgent. Non tentare mai di cambiare lo stato del sistema."
)

class ObserverAgent:
    def __init__(self, api_key, base_url, model, obs_url):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.obs_url = obs_url.rstrip("/")
        
        # Definizione dei tool MCP disponibili per l'osservazione [cite: 58]
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_cluster_status",
                    "description": "Ottieni lo stato dei sensori attivi su Kubernetes.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_telemetry_summary",
                    "description": "Ottieni la media delle temperature recenti da InfluxDB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes_ago": {"type": "integer", "default": 5}
                        }
                    }
                }
            }
        ]

    def call_mcp(self, name, args):
        """Chiamata al server MCP di Osservazione (Porta 8101)"""
        resp = requests.post(f"{self.obs_url}/tool", json={"name": name, "args": args})
        return resp.json().get("result", {})

    def run(self):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Esegui un controllo di routine dei sensori e delle temperature."}
        ]

        # Ciclo di ragionamento dell'LLM (Tool Calling)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools
        )
        
        msg = response.choices[0].message
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                result = self.call_mcp(tool_call.function.name, json.loads(tool_call.function.arguments))
                messages.append(msg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(result)
                })
            
            # Generazione diagnosi finale
            final_resp = self.client.chat.completions.create(model=self.model, messages=messages)
            return final_resp.choices[0].message.content
        return msg.content