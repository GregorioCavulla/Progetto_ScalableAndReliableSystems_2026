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
        print("\n" + "="*80)
        print("🏥 HEALTH AGENT - INIZIO CICLO DI MONITORAGGIO")
        print("="*80)
        
        user_message = "Controlla la salute della flotta di droni e prendi azioni correttive se necessario."
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

    
        print("\n⏳ Avvio loop di ragionamento LLM...")
        
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
                    
                    print(f"\n📢 RISPOSTA FINALE DEL LLM:\n{final_content}")
                    print(f"\n{'='*80}\n")
                    return final_content
                
                # 2. ESECUZIONE TOOL: L'LLM vuole raccogliere altri dati o eseguire azioni
                tool_count = len(msg.tool_calls)
                print(f"\n🔧 L'LLM VUOLE USARE {tool_count} TOOL:")
                
                # Salviamo l'intenzione dell'LLM nella cronologia
                messages.append(msg)
                
                # Eseguiamo tutti i tool che ha richiesto
                for i, tool_call in enumerate(msg.tool_calls, 1):
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"\n   [{i}] 🛠️  Eseguo Tool: {tool_name}")
                    print(f"       Argomenti: {tool_args}")
                    
                    # Chiama il server MCP
                    result = self.call_mcp(tool_name, tool_args)
                    print(f"       ✅ Risultato: {result}")
                    
                    # Salviamo il risultato del tool nella cronologia
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(result)
                    })
                
                print("\n⏳ Re-invio i risultati all'LLM per decidere il prossimo step...")
                # Il ciclo riparte! Ora l'LLM vedrà i dati e deciderà il prossimo tool da usare.
                
            except Exception as e:
                print(f"\n❌ ERRORE NEL LOOP AGENTE: {e}")
                return f"Errore: {e}"