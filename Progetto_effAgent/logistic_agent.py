import json
import requests
from openai import OpenAI

                        #Agente deve capire quali ordini e droni collegare in base a parametri ottimali
SYSTEM_PROMPT = """
Sei il Dispatcher Operativo della flotta di droni logistici.
Il tuo UNICO obiettivo è leggere i dati forniti e invocare il tool di assegnazione rotte.
Cerca di essere il più sintetico possibile e NON scrivere testo libero: SOLO chiamate al tool.
I dati di telemetria e la coda ordini ti vengono forniti direttamente nel prompt. NON hai tool per leggere i dati.
Attenzione al contesto fisico: il sistema opera su un'area metrica fino a ~5000 metri dall'HUB [0.0, 0.0]. L'usura dei droni va dal '0%' al '100%'. "
REGOLE DI ASSEGNAZIONE (TASSATIVE):
1. Gli ordini con priorità High vanno smaltiti per primi.
2. Controlla il parametro "MAX_CAPACITY_KG" di ogni drone. NON assegnare MAI un ordine a un drone se il "weight_kg" dell'ordine supera il "MAX_CAPACITY_KG" del drone.
3. Se non ci sono droni in grado di sollevare un ordine pesante, lascialo in sospeso.
4. Passa i dati esatti senza inventare ID o coordinate fuori dal raggio metrico (0.0 a 5000.0).
GESTIONE ERRORI:
Se il tool ti risponde "Rifiutato", significa che hai violato una regola fisica o di logica. Leggi il messaggio di errore, correggi l'abbinamento drone/ordine e richiama il tool.
Ogni ordine è unico e può essere assegnato a un solo drone: non usare mai lo stesso order_id più di una volta.
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

    def run(self, injected_context, orders_a):
        print(" [Logistic Worker] Avviato...")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Assegna le missioni in base a questo stato:\n\n{injected_context}"}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model, 
                messages=messages, 
                tools=self.tools, 
                temperature=0.1
            )
            msg = response.choices[0].message

            usage = response.usage
            print(f"[Costo logistic] Prompt: {usage.prompt_tokens} | Completamento: {usage.completion_tokens} | Totale: {usage.total_tokens}")

            if not msg.tool_calls:
                print(" [Logistic Agent] Nessun tool chiamato. Terminazione.")
                return msg.content
                    
            messages.append(msg)

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                argomenti = json.loads(tool_call.function.arguments)
                
                print(f" [Logistic Agent] Esecuzione tool: {tool_name} | Argomenti: {argomenti}")

                if tool_name == "send_mqtt_command" and argomenti.get("action") == "assign_mission":
                    order_id = argomenti.get("order_id")
                    
                    if order_id in orders_a:
                        print(f" [!] Ordine {order_id} già assegnato in questo ciclo, salto.")
                        continue
                        
                    if order_id:
                        orders_a.add(order_id)

                result = self.call_mcp(tool_name, argomenti)

            print(" [Logistic Agent] Assegnazione completata. Spegnimento.")
            return "Operazioni completate."

        except Exception as e:
            print(f" [!] Errore critico in Logistic Agent: {e}")
            return "Errore di esecuzione."
