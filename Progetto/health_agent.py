import os
import json
import requests
import time
from openai import OpenAI

# Prompt di sistema per l'Health Agent
SYSTEM_PROMPT = (
    "Sei l'HealthAgent del sistema di droni. Il tuo compito principale è monitorare la salute della flotta e scalare il numero di droni quando necessario per gestire gli ordini pendenti o sostituire droni in manutenzione. "
    "Interroga regolarmente lo stato dei droni, la telemetria e gli ordini pendenti per prendere decisioni informate. "
    "1. Monitora l'usura dei droni (0-100%). Se un drone tocca il '95%', va in MAINTENANCE autonoma. "
    "2. Se un drone in MAINTENANCE è lontano dall'HUB (lat: 0.0, lon: 0.0), è precipitato: scala immediatamente per recupero senza chiedere permessi. "
    "3. Scala il numero di droni se non ce ne sono abbastanza per gli ordini pendenti o per sostituire quelli in manutenzione. Decidi tu quanti droni aggiungere (es. se ci sono 10 ordini pendenti e 3 droni attivi, scala a 5-6). "
    "4. Se lo scaling supera 6 droni totali, usa 'request_human_approval' con action_type='scale_drone_deployment', reason appropriato, e payload={'replicas': numero}. Poi fermati e aspetta. "
    "5. Al primo giro, usa sempre 'check_pending_approvals': se vedi 'approved', NON scalare tu (l'infrastruttura lo fa automaticamente al click umano). "
    "Usa questi comandi: "
    "- get_drones_status: per numero droni attivi. "
    "- get_drones_telemetry: per stato batteria, usura, posizione. "
    "- get_pending_orders: per ordini pendenti. "
    "- scale_drone_deployment: per scalare (solo se <=6 o force). "
    "- request_human_approval: per scaling >6. "
    "- check_pending_approvals: per controllare approvazioni."
)
# TODO: valutare il guadagno in base a incasso ordine - wear e batteria drone (costi stimati per ogni missione) e usarlo come metrica per decidere le assegnazioni

# TODO: pulire il log

class HealthAgent:
    def __init__(self, api_key, base_url, model, mcp_url, token, max_iterations=4):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        # Limite di iterazioni di ragionamento per evitare loop infiniti e spreco di token
        self.max_iterations = max_iterations
        
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
        start_time = time.time()
        
        user_message = "Controlla la salute della flotta di droni e prendi azioni correttive se necessario."
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

    
        print(" Ragionamento in corso...")

        # Contatore delle iterazioni di ragionamento (rounds con tool calls)
        iterations = 0

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
                    
                    print(f"Tempo di ragionamento: {time.time() - start_time:.2f} secondi")
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

                # Aumenta il contatore delle iterazioni e verifica il limite
                iterations += 1
                if iterations >= self.max_iterations:
                    abort_msg = (
                        f"Interruzione: raggiunto il limite di {self.max_iterations} iterazioni di ragionamento. "
                        "Operazione abortita per evitare spreco di token."
                    )
                    print(abort_msg)
                    return abort_msg
                
            except Exception as e:
                print(f" Errore: {e}")
                return f"Errore: {e}"