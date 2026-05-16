import json
import requests
from openai import OpenAI

                        #Agente deve capire quali ordini e droni collegare in base a parametri ottimali
SYSTEM_PROMPT = """
Sei il Dispatcher Operativo della flotta di droni logistici.
Il tuo UNICO obiettivo è leggere i dati forniti e invocare il tool di assegnazione rotte.
I dati di telemetria e la coda ordini ti vengono forniti direttamente nel prompt. NON hai tool per leggere i dati.
Attenzione al contesto fisico: il sistema opera su un'area metrica fino a ~5000 metri dall'HUB [0.0, 0.0]. L'usura dei droni va dal '0%' al '100%'. "
    I droni scaricano la batteria molto più in fretta e volano più lenti in proporzione al 'weight_kg' dell'ordine assegnato (max 5.0kg). "
    Quando stabilisci le tue scelte, bilancia sempre: 
    1. La priorità dell'ordine ('high', 'normal', 'low'). 
    2. Il 'weight_kg' da sollevare contro la percentuale di batteria del drone. 
    3. Il tasso di usura del mezzo. "
    Se un ordine prioritario è molto pesante (es. 4-5 kg), NON assegnargli un drone logorato (>80%) o con poca batteria, l'anomalia causerebbe uno schianto e avarierebbe il mezzo. "
REGOLE OBBLIGATORIE:
1. NON spiegare il tuo ragionamento in nessun caso.
2. NON scrivere testo libero, saluti, preamboli o conclusioni.
3. Usa ESCLUSIVAMENTE il tool a tua disposizione send_mqtt_command per assegnare i droni agli ordini.
4. Fai un'unica chiamata al tool passando tutti gli abbinamenti drone-ordine in una volta sola.
5. Smetti di generare testo non appena hai chiamato il tool.
"""

class LogisticAgent:
    def __init__(self, api_key, base_url, model, mcp_url, token):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_mqtt_command",
                    "description": "Invia un comando MQTT a un drone per assegnare una missione.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "action": {"type": "string", "enum": ["assign_mission"]},
                            "order_id": {"type": "string"},
                            "target_lat": {"type": "number"},
                            "target_lon": {"type": "number"}
                        },
                        "required": ["target", "action", "order_id"]
                    }
                }
            }
        ]

    def call_mcp(self, name, args):
        headers = {"X-MCP-Token": self.token}
        resp = requests.post(f"{self.mcp_url}/tool", json={"name": name, "args": args}, headers=headers)
        return resp.json().get("result", {})

    def run(self, injected_context):
        print(" [Logistic Worker] Avviato...")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Assegna le missioni in base a questo stato:\n\n{injected_context}"}
        ]

        while True:
            try:
                response = self.client.chat.completions.create(model=self.model, messages=messages, tools=self.tools, temperature=0.2)
                msg = response.choices[0].message

                usage = response.usage
                print(f"[Costo logistic] Prompt: {usage.prompt_tokens} | Completamento: {usage.completion_tokens} | Totale: {usage.total_tokens}")

                if not msg.tool_calls:
                            print(" [Logistic Agent] Nessun tool chiamato. Terminazione.")
                            return msg.content
                        
                messages.append(msg)


                for tool_call in msg.tool_calls:
                            nome_tool = tool_call.function.name
                            argomenti = json.loads(tool_call.function.arguments)
                            
                            print(f" [Logistic Agent] Esecuzione tool MCP: {nome_tool} | Argomenti: {argomenti}")
                            
                        
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
