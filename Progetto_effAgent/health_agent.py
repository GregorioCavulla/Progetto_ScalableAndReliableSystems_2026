import json
import requests
from openai import OpenAI
                                            #Sostituire LOGICA DI SCALING --> agente deve capire quanti droni scalare in base a necessità
SYSTEM_PROMPT = """ 
Sei il Direttore dell'Infrastruttura (Health Agent) della flotta di droni.
Il tuo UNICO obiettivo è leggere lo stato del sistema e decidere se scalare i droni o richiedere manutenzione, usando esclusivamente i tool a disposizione.
REGOLE OBBLIGATORIE
1. NON spiegare il tuo ragionamento. NON scrivere testo libero. Chiama direttamente il tool. 
2. Scala il numero di droni se non ce ne sono abbastanza per gli ordini pendenti o per sostituire quelli in manutenzione. 
3. Calcola il numero TOTALE desiderato di repliche. Il parametro 'replicas' del tool DEVE rappresentare sempre lo stato finale, ovvero la somma tra i droni operativi attuali e i nuovi droni di cui hai bisogno.
   - Calcola il fabbisogno di droni extra: ad esempio, usa circa la metà degli ordini pendenti.
   - Somma questo fabbisogno ai droni totali operativi attuali che leggi nello stato.
   - Esempio pratico: se lo stato ti indica 6 droni operativi e 4 ordini pendenti (quindi decidi di aggiungere 2 droni), devi chiamare il tool passando ESATTAMENTE {'replicas': 8}. NON passare mai solo il numero dei droni da aggiungere.
4. - Se il numero totale di repliche necessarie è <= 6, usa DIRETTAMENTE il tool `scale_drone_deployment`.
   - Se il numero totale di repliche necessarie è > 6, NON PUOI scalare da solo. DEVI usare obbligatoriamente `request_human_approval` passando l'azione richiesta.
5. - Se controlli le approvazioni con `check_pending_approvals` e vedi che una tua richiesta precedente è in stato "approved", l'infrastruttura è già stata scalata istantaneamente dal Gateway Umano. NON chiamare il tool `scale_drone_deployment`. Considera la pratica conclusa con successo e termina l'esecuzione.
6. Se devi scalare i droni e il numero totale supera le 6 repliche:
   -> STEP 1: Chiama SEMPRE prima `check_pending_approvals`.
   -> STEP 2: Analizza la risposta del tool:
      - SE ci sono approvazioni nella lista "pending": NON FARE NULLA. L'operatore umano sta ancora valutando la richiesta. Termina l'esecuzione.
      - SE la lista "pending" è vuota (nessuna richiesta in corso per quel volume): Chiama `request_human_approval` specificando quante repliche ti servono. NON controllare di nuovo in questo turno.
7. Smetti di generare testo non appena hai chiamato il tool.
"""

class HealthAgent:
    def __init__(self, api_key, base_url, model, mcp_url, token):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "scale_drone_deployment",
                    "description": "Scala il numero di droni su Kubernetes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "replicas": {"type": "integer"},
                            "force": {"type": "boolean", "description": "Usa true per applicare lo scaling dopo approvazione umana."}
                        },
                        "required": ["replicas"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_human_approval",
                    "description": "Chiedi autorizzazione per azioni ad alto impatto (es. scaling > 6).",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "action_type": {"type": "string",
                            "enum": ["scale_drone_deployment"]
                            }, 
                            "payload": {"type": "object", "description": "Dettagli dell'azione, max 5 words. es. {'replicas': 7}"},
                            "reason": {"type": "string"}
                        },
                        "required": ["action_type", "payload", "reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_pending_approvals",
                    "description": "Controlla lo stato delle richieste di approvazione.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "request_id": {"type": "string", "description": "Controlla lo stato di una richiesta specifica."}
                        }
                    }
                }
            }
        ]

    def call_mcp(self, name, args):
        headers = {"X-MCP-Token": self.token}
        try:
            resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers)
            try:
                return resp.json().get("result", {})
            except json.decoder.JSONDecodeError:
                print(f"Server MCP ha restituito un errore {resp.status_code}")
                return {"error": "Server MCP Error"}
                
        except requests.exceptions.RequestException as e:
            print(f"Errore di rete contattando MCP: {e}")
            return {"error": "Rete/Timeout MCP"}
        

    def run(self, injected_context):
        print(" [Health Agent] Analisi stato infrastruttura avviata...")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Stato:\n\n{injected_context}"}
        ]

        MAX_AGENT_STEPS = 3

        for step in range(MAX_AGENT_STEPS):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, 
                    messages=messages, 
                    tools=self.tools,
                    temperature=0.1
                )
                
                msg = response.choices[0].message

                usage = response.usage
                print(f" [Costo health] Prompt: {usage.prompt_tokens} | Completamento: {usage.completion_tokens} | Totale: {usage.total_tokens}")
                
                if not msg.tool_calls:
                    print(" [Health Agent] Nessun tool chiamato. Terminazione naturale.")
                    return msg.content
                
                messages.append(msg)
                
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name
                    argomenti = json.loads(tool_call.function.arguments)
                    
                    print(f" [Health Agent] Esecuzione tool MCP: {tool_name} | Argomenti: {argomenti}")
                    
                    result = self.call_mcp(tool_name, argomenti)
                    
                    if tool_name == "request_human_approval":
                        print(" [Health Agent] Richiesta inviata. Disconnessione in attesa dell'umano...")
                        return "Richiesta in attesa. Spegnimento."
                    
                    if tool_name == "scale_drone_deployment":
                        print(f" [Health Agent] Comando di scaling inviato ({argomenti}). Disconnessione...")
                        return f"Scaling avviato con successo. Risposta: {result}"
                    
                    messages.append({
                        "role": "tool", 
                        "tool_call_id": tool_call.id, 
                        "name": tool_name, 
                        "content": json.dumps(result)
                    })
                    
                    if tool_name == "check_pending_approvals":
                        pending = result.get("pending", []) if isinstance(result, dict) else []
                        if len(pending) > 0:
                            print(" [Health Agent] Approvazione in corso. Lascio lavorare l'operatore. Disconnessione...")
                            return "Azione gestita dal livello umano. Spegnimento."
                        else:
                            print(" [Health Agent] Nessuna approvazione pendente: valuto il prossimo tool.")
                            
            except Exception as e:
                print(f" [!] Errore critico in Health Agent: {e}")
                return "Errore di esecuzione."

        error_msg = " [!] INTERVENTO DI SICUREZZA: Raggiunto il limite massimo di iterazioni. Agente disconnesso."
        print(error_msg)
        return error_msg
