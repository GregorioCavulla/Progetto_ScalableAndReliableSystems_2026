import json
import requests
from openai import OpenAI

SYSTEM_PROMPT = (
    "Sei il RemediationAgent. Riceverai un triage dall'ObserverAgent. "
    "Il tuo compito è risolvere i problemi usando i tool MCP. "
    "REGOLE DI SICUREZZA:\n"
    "1. Se devi scalare oltre 6 repliche, DEVI chiedere approvazione umana.\n"
    "2. Comandi critici (REBOOT, SPEGNI) richiedono approvazione umana.\n"
    "3. Se la situazione è ambigua, escala all'operatore umano."
)

class RemediationAgent:
    def __init__(self, api_key, base_url, model, ops_url, token):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.ops_url = ops_url.rstrip("/")
        self.token = token
        
        # Tool operativi [cite: 58, 105]
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_mqtt_command",
                    "description": "Invia un comando MQTT a un sensore smart.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "command": {"type": "string"}
                        },
                        "required": ["target", "command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "scale_sensor_deployment",
                    "description": "Scala il numero di pod dei sensori su Kubernetes.",
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
        """Chiamata al server MCP di Operatività (Porta 8102) con Token"""
        headers = {"X-MCP-Token": self.token}
        resp = requests.post(f"{self.ops_url}/tool", json={"name": name, "args": args}, headers=headers)
        return resp.json().get("result", {})

    def run(self, diagnosis):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Diagnosi dell'Observer: {diagnosis}"}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools
        )
        
        msg = response.choices[0].message
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                result = self.call_mcp(tool_call.function.name, json.loads(tool_call.function.arguments))
                # Se il layer MCP nega l'azione, l'LLM lo saprà dal risultato 'allowed: False'
                messages.append(msg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(result)
                })
            
            final_resp = self.client.chat.completions.create(model=self.model, messages=messages)
            return final_resp.choices[0].message.content
        return msg.content