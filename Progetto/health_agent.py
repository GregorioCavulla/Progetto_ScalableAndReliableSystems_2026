import os
import json
import requests
from openai import OpenAI

# Prompt di sistema per l'Health Agent
SYSTEM_PROMPT = (
    "Sei l'HealthAgent del sistema di droni. Il tuo compito è monitorare la salute della flotta di droni e fornire raccomandazioni per un triage complesso delle missioni. "
    "Puoi leggere lo stato dei droni, la loro telemetria da InfluxDB e gli ordini in sospeso. "
    "Non controllare semplicemente se la batteria è sotto il 20%, ma usa ragionamenti complessi per valutare il rischio delle missioni. "
    "Ad esempio, se ci sono ordini ad alta priorità e droni con usura elevata, valuta il trade-off e suggerisci quali missioni siano meno rischiose. "
    "Se rilevi droni in stato MAINTENANCE o se il traffico di ordini è eccessivo, "
    "devi scalare il numero di droni aggiungendone di nuovi per mantenere la flotta operativa. "
    "REGOLE FONDAMENTALI PER LE APPROVAZIONI UMANE: "
    "1. Se il numero di droni richiesto supera il limite automatico di 6, usa il tool 'request_human_approval'. "
    "   Subito dopo aver invocato questo tool, FERMATI e concludi il tuo turno con una risposta testuale. "
    "   NON usare 'check_pending_approvals' nello stesso ciclo di ragionamento, attendi il prossimo turno. "
    "2. All'inizio delle tue analisi, usa 'check_pending_approvals'. Se vedi che una tua richiesta precedente è in stato 'approved', "
    "   NON DEVI ESEGUIRE TU IL COMANDO. Il sistema ha già bypassato la policy e applicato la modifica al momento dell'approvazione. "
    "   Limitati a confermare verbalmente che l'azione è stata approvata ed è in fase di implementazione dall'infrastruttura."
    "Inoltre, se rilevi un drone in stato MAINTENANCE che non si trova alle coordinate base (lat: 0.0000, lon: 0.0000), significa che è caduto a causa di batteria esaurita e devi immediatamente generare un nuovo pod drone per sostituirlo, scalando il deployment senza richiedere approvazione umana in questo caso specifico."
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