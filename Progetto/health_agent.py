import os
import json
import requests
from openai import OpenAI

# Prompt di sistema per l'Health Agent
SYSTEM_PROMPT = (
    "Sei l'HealthAgent del sistema di droni. Il tuo compito è il monitoraggio vitale della flotta prendendo decisioni di triage di alto livello. "
    "Interroga lo stato, la telemetria da InfluxDB e monitora il carico (ordini). "
    "1. L'usura dei droni è percentuale (0-100%). Se un drone tocca il '95%' andrà in MAINTENANCE autonoma rientrando alla base, ritirato dai cieli attivi per evitare un guasto catastrofico in fase di volo. "
    "2. Se, tuttavia, rilevi un drone in stato MAINTENANCE che si è fermato lontano dall'HUB, ovvero NON alle coordinate base (lat: 0.0, lon: 0.0), significa che è precipitato in mezzo all'area di copertura a causa di un prosciugamento fatale della batteria. "
    "   Solo ed esclusivamente a fronte di droni precipitati fuori base, scala l'infrastruttura (aggiungendo nuovi pod su Kubernetes) per garantire un recupero immediato dei livelli di servizio sul territorio, senza chiedere permessi ai logistici. "
    "3. Per qualsiasi altra azione di scala basata sull'eccessivo traffico (es. se la somma di droni attivi non smaltisce o se serve salire oltre a 6 droni attivi), invoca obbligatoriamente il tool 'request_human_approval' prima di intervenire. "
    "   Dopo l'invocazione di 'request_human_approval', fermati. NON usare 'check_pending_approvals' nel tuo stesso loop, aspetta un turno intero. "
    "4. Al primo giro, usa sempre 'check_pending_approvals': se rilevi uno status 'approved', annotalo vocalmente rallegrandoti, ma NON invocare tu il deployment scalando: l'infrastruttura sottostante la applica in automatico al click umano."
)
# TODO: valutare il guadagno in base a incasso ordine - wear e batteria drone (costi stimati per ogni missione) e usarlo come metrica per decidere le assegnazioni

# TODO: pulire il log

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
                    "name": "get_pending_orders",
                    "description": "Ottieni gli ordini in sospeso dal sistema.",
                    "parameters": {"type": "object", "properties": {}}
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
                            "reason": {"type": "string"},
                            "payload": {"type": "object"}
                        },
                        "required": ["action_type", "reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_pending_approvals",
                    "description": "Controlla lo stato delle richieste di approvazione umana pendenti.",
                    "parameters": {"type": "object", "properties": {}}
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

    def run(self):
        print("\n HEALTH AGENT - MONITORAGGIO SALUTE FLOTTA")
        
        user_message = "Controlla la salute della flotta di droni e prendi azioni correttive se necessario."
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