import json
import requests
from openai import OpenAI

SYSTEM_PROMPT = """ 
Sei il Direttore dell'Infrastruttura (Health Agent) della flotta di droni.
Il tuo UNICO obiettivo è leggere lo stato del sistema e decidere se scalare i droni o richiedere manutenzione, usando esclusivamente i tool a disposizione.
REGOLE OBBLIGATORIE
1. NON spiegare il tuo ragionamento. NON scrivere testo libero. Chiama direttamente il tool.
DIRETTIVE DI SICUREZZA ASSOLUTE (TASSATIVE):
- Se il numero TOTALE di repliche che ritieni necessario è MINORE O UGUALE A 6 (Repliche <= 6): hai piena autonomia. Chiama DIRETTAMENTE il tool `scale_drone_deployment`.
- Se il numero TOTALE di repliche necessarie è MAGGIORE DI 6 (Repliche > 6): NON HAI L'AUTORIZZAZIONE per scalare da solo. È VIETATO chiamare `scale_drone_deployment`. DEVI usare obbligatoriamente il tool `request_human_approval`.
4. CONTRATTO DELLE APPROVAZIONI: `check_pending_approvals` ritorna SOLO le richieste ancora pending. Le approvate vengono eseguite direttamente dalla dashboard umana sul cluster: tu te ne accorgerai al prossimo giro leggendo lo stato reale del cluster, NON monitorando le approvazioni. Una richiesta che sparisce significa che è stata processata (approvata o rifiutata) — fidati dello stato del cluster.
5. Se devi scalare i droni e il numero totale supera le 6 repliche:
   -> STEP 1: Chiama SEMPRE prima `check_pending_approvals`.
   -> STEP 2: Analizza la risposta:
      - SE la lista "pending" NON è vuota: hai già una richiesta in corso. NON FARE NULLA. Termina l'esecuzione.
      - SE la lista "pending" è vuota: Chiama `request_human_approval` e termina.
6. Smetti di generare testo non appena hai chiamato il tool.
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
                            "replicas": {"type": "integer"}
                            #"force": {"type": "boolean", "description": "Usa true per applicare lo scaling."}
                        },
                        "required": ["replicas"],
                        "additionalProperties": False 
                    },
                    "strict": True
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
                            "action_type": {
                                "type": "string",
                                "enum": ["scale_drone_deployment", "send_mqtt_command"] 
                            }, 
                            "payload": {"type": "object"},
                            "reason": {"type": "string"}
                        },
                        "required": ["action_type", "payload", "reason"],
                        "additionalProperties": False
                    },
                    "strict": True
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
                            "request_id": {"type": "string"}
                        },
                        "additionalProperties": False
                    },
                    "strict": True
                }
            }
        ]
        self.valid_tools = ["scale_drone_deployment", "request_human_approval", "check_pending_approvals"]

    def call_mcp(self, name, args):
        headers = {"X-MCP-Token": self.token}
        try:
            resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers, timeout=5)
            try:
                return resp.json().get("result", {})
            except json.decoder.JSONDecodeError:
                return {"error": "Server MCP Error JSON"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Rete/Timeout MCP: {e}"}
        
    def run(self, injected_context):
        print(" [Health Agent] Analisi stato infrastruttura avviata...")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Stato:\n\n{injected_context}"}
        ]

        MAX_AGENT_STEPS = 3
        consecutive_errors = 0 

        for step in range(MAX_AGENT_STEPS):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, 
                    messages=messages, 
                    tools=self.tools,
                    temperature=0.2,
                    max_tokens=2050 
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
                    
                    if tool_name not in self.valid_tools:
                        error_msg = f"Errore: Tool '{tool_name}' non esiste. Usa solo tool autorizzati."
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps({"error": error_msg})})
                        continue

                    try:
                        argomenti = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        error_msg = "Errore: Argomenti JSON malformati. Correggi la sintassi e riprova."
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps({"error": error_msg})})
                        consecutive_errors += 1
                        continue

                    print(f" [Health Agent] Esecuzione tool: {tool_name} | Args: {argomenti}")
                    result = self.call_mcp(tool_name, argomenti)

                    if isinstance(result, dict) and result.get("allowed") is False:
                        consecutive_errors += 1
                        if consecutive_errors >= 2:
                            print(" Block, l'agente continua a fallire la chiamata al tool.")
                            return "Intervento bloccato per ripetuti errori di policy."
                    else:
                        consecutive_errors = 0
                    
                    if tool_name == "request_human_approval":
                        return "Richiesta in attesa. Spegnimento."
                    
                    if tool_name == "scale_drone_deployment" and isinstance(result, dict) and result.get("status") == "success":
                        return f"Scaling avviato con successo."
                    
                    messages.append({
                        "role": "tool", 
                        "tool_call_id": tool_call.id, 
                        "name": tool_name, 
                        "content": json.dumps(result)
                    })
                    
                    if tool_name == "check_pending_approvals":
                        pending = result.get("pending", []) if isinstance(result, dict) else []
                        if len(pending) > 0:
                            return "Azione gestita dal livello umano. Spegnimento."
                            
            except Exception as e:
                print(f" Errore critico in Health Agent: {e}")
                return "Errore di esecuzione."

        return " Limite iterazioni raggiunto."