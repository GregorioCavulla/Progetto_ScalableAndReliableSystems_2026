import json
import requests
from openai import OpenAI

SYSTEM_PROMPT = """
Sei il Direttore dell'Infrastruttura (Health Agent) della flotta di droni.
Il tuo UNICO obiettivo è leggere lo stato del sistema e decidere se scalare i droni o richiedere manutenzione, usando esclusivamente i tool a disposizione.
REGOLE TASSATIVE
1. EFFICIENZA: NON spiegare il tuo ragionamento. NON scrivere testo libero. Chiama direttamente il tool.
2. LOGICA DI SCALING: Se ci sono ordini pendenti e zero droni disponibili, calcola i droni necessari e aggiungi 1 drone ogni 2 ordini pendenti (es. 5 ordini -> 3 droni)
3. GUARDRAIL ECONOMICO (HUMAN-IN-THE-LOOP): 
   - Se il numero totale di repliche necessarie è <= 6, usa DIRETTAMENTE il tool `scale_drone_deployment`.
   - Se il numero totale di repliche necessarie è > 6 (alto impatto sui costi cloud), NON PUOI scalare da solo. DEVI usare obbligatoriamente `request_human_approval` passando l'azione richiesta
4. WORKFLOW DELLE APPROVAZIONI (FONDAMENTALE): 
   - Se controlli le approvazioni con `check_pending_approvals` e vedi che una tua richiesta precedente è "APPROVATA" (o "GRANTED"), DEVI IMMEDIATAMENTE chiamare il tool `scale_drone_deployment` con il numero di repliche autorizzato.
   - NON fermarti e NON rispondere a testo dopo aver letto l'approvazione: esegui subito lo scaling.
5. Smetti di generare testo non appena hai chiamato il tool.
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
                    "parameters": {"type": "object", "properties": {"replicas": {"type": "integer"}}, "required": ["replicas"]}
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
                            "payload": {"type": "object", "description": "Dettagli dell'azione, es. {'replicas': 7}"},
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
                    "parameters": {"type": "object", "properties": {}}
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
                {"role": "user", "content": f"Verifica questo stato e usa i tool per agire se necessario:\n\n{injected_context}"}
            ]

            while True:
                try:
        
                    response = self.client.chat.completions.create(
                        model=self.model, 
                        messages=messages, 
                        tools=self.tools,
                        temperature=0.1
                    )
                    
                    msg = response.choices[0].message
                    
                    # Tracciamento costi
                    usage = response.usage
                    print(f" [Costo health] Prompt: {usage.prompt_tokens} | Completamento: {usage.completion_tokens} | Totale: {usage.total_tokens}")
                    

                    if not msg.tool_calls:
                        print(" [Health Agent] Nessun tool chiamato. Terminazione naturale.")
                        return msg.content
                    

                    messages.append(msg)
                    
                    for tool_call in msg.tool_calls:
                        nome_tool = tool_call.function.name
                        argomenti = json.loads(tool_call.function.arguments)
                        
                        print(f" [Health Agent] Esecuzione tool MCP: {nome_tool} | Argomenti: {argomenti}")
                        
                      
                        result = self.call_mcp(nome_tool, argomenti)
                        
                        # Rimettiamo il risultato nel contesto affinché l'LLM possa leggerlo al prossimo giro
                        messages.append({
                            "role": "tool", 
                            "tool_call_id": tool_call.id, 
                            "name": nome_tool, 
                            "content": json.dumps(result)
                        })

                except Exception as e:
                    print(f" [!] Errore critico in Health Agent: {e}")
                    return "Errore di esecuzione."