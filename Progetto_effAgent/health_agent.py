import json
import requests
from openai import OpenAI
                                            #Sostituire LOGICA DI SCALING --> agente deve capire quanti droni scalare in base a necessità
SYSTEM_PROMPT = """ 
Sei il Direttore dell'Infrastruttura (Health Agent) della flotta di droni. Il tuo sistema è ASINCRONO. Non puoi aspettare le risposte in tempo reale.
Il tuo UNICO obiettivo è leggere lo stato del sistema e decidere se scalare i droni o richiedere manutenzione, usando esclusivamente i tool a disposizione.
REGOLE OBBLIGATORIE
1. NON spiegare il tuo ragionamento. NON scrivere testo libero. Chiama direttamente il tool. 
2. Scala il numero di droni se non ce ne sono abbastanza per gli ordini pendenti o per sostituire quelli in manutenzione. Decidi tu quanti droni aggiungere (es. se ci sono 10 ordini pendenti e 3 droni attivi, scala a 5-6 droni). 
3. - Se il numero totale di repliche necessarie è <= 6, usa DIRETTAMENTE il tool `scale_drone_deployment`.
   - Se il numero totale di repliche necessarie è > 6, NON PUOI scalare da solo. DEVI usare obbligatoriamente `request_human_approval` passando l'azione richiesta.
4. - Se controlli le approvazioni con `check_pending_approvals` e vedi che una tua richiesta precedente è "APPROVATA" (o "GRANTED"), valuta se il numero di repliche autorizzato soddisfa la tua domanda corrente.
     - SE l'approvazione autorizza almeno il numero di droni necessari: DEVI IMMEDIATAMENTE chiamare il tool `scale_drone_deployment` con il numero di repliche autorizzato e `force=True`.
     - SE l'approvazione è troppo bassa rispetto al bisogno reale: IGNORA quell'approvazione e richiedi una nuova autorizzazione per il numero richiesto.
     - NON fermarti e NON rispondere a testo dopo aver letto l'approvazione: esegui subito lo scaling se l'approvazione è valida.
5. Se devi scalare i droni e ce ne sono più di 6,-> STEP 1: Chiama SEMPRE prima `check_pending_approvals`.
   -> STEP 2: Analizza ESATTAMENTE la risposta del tool:
      - SE ci sono approvazioni in "approved": usa l'approvazione valida che soddisfa il bisogno attuale, o richiedi una nuova approvazione se serve più capacità.
      - SE ci sono approvazioni in "pending": NON FARE NULLA. Hai finito.
      - SE le liste sono vuote (nessuna richiesta in corso): Chiama `request_human_approval` specificando quante repliche ti servono. NON controllare di nuovo.
6. Smetti di generare testo non appena hai chiamato il tool.
"""

class HealthAgent:
    def __init__(self, api_key, base_url, model, mcp_url, token):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        self.last_approval_request_id = None

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
                            "action_type": {"type": "string"}, 
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
                {"role": "system", "content": SYSTEM_PROMPT}
            ]

            if self.last_approval_request_id:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Ultima richiesta di approvazione umana pendente: {self.last_approval_request_id}. "
                        "Se puoi, controlla lo stato di questa richiesta usando check_pending_approvals con request_id.")
                })

            messages.append({"role": "user", "content": f"Stato:\n\n{injected_context}"})

            while True:
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
                        
                        #Spegni se richiede approvazione
                        if tool_name == "request_human_approval":
                            if isinstance(result, dict) and result.get("request_id"):
                                self.last_approval_request_id = result["request_id"]
                            print(" [Health Agent] Richiesta inviata. Disconnessione asincrona in attesa dell'umano...")
                            return "Richiesta in attesa. Spegnimento."
                        
                        if tool_name == "scale_drone_deployment":
                            if argomenti.get("force"):
                                self.last_approval_request_id = None
                            print(f" [Health Agent] Comando di scaling inviato ({argomenti}). Disconnessione per permettere l'avvio dei pod...")
                            return f"Scaling avviato con successo. Risposta: {result}"
                        
                        # Rimettiamo il risultato nel contesto per il tool check_pending_approvals
                        messages.append({
                            "role": "tool", 
                            "tool_call_id": tool_call.id, 
                            "name": tool_name, 
                            "content": json.dumps(result)
                        })
                        
                        # Se ci sono richieste ancora in sospeso, interrompi il ciclo.
                        if tool_name == "check_pending_approvals":
                            pending = result.get("pending") if isinstance(result, dict) else None
                            approved = result.get("approved") if isinstance(result, dict) else None
                            if isinstance(pending, list) and len(pending) > 0:
                                print(" [Health Agent] Ci sono richieste in sospeso. Disconnessione asincrona...")
                                return "In attesa dell'umano. Spegnimento."
                            if isinstance(approved, list) and len(approved) > 0:
                                print(" [Health Agent] Trovata approvazione già concessa. Continuo per eseguire lo scaling.")
                            else:
                                print(" [Health Agent] Nessuna approvazione pendente o approvata: continuo a valutare il prossimo tool.")
                            


                except Exception as e:
                    print(f" [!] Errore critico in Health Agent: {e}")
                    return "Errore di esecuzione."
