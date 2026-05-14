import os
import time
import json
import threading
import requests
import sys
import hashlib
sys.stdout.reconfigure(line_buffering=True)
from openai import OpenAI
from health_agent import HealthAgent
from logistic_agent import LogisticAgent

API_BASE = "https://litellm-proxy-1013932759942.europe-west8.run.app/v1"
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = "gemini-2.5-pro"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8101")
MCP_TOKEN = os.getenv("MCP_TOKEN", "segreto-universitario")

health_agent = HealthAgent(API_KEY, API_BASE, MODEL_NAME, MCP_SERVER_URL, MCP_TOKEN)
logistic_agent = LogisticAgent(API_KEY, API_BASE, MODEL_NAME, MCP_SERVER_URL, MCP_TOKEN)
llm_client = OpenAI(api_key=API_KEY, base_url=API_BASE)

def fetch_global_state():
    """Recupera tutti i dati dal server MCP con semplici e veloci chiamate HTTP."""
    headers = {"X-MCP-Token": MCP_TOKEN}
    base_url = f"{MCP_SERVER_URL.rstrip('/')}/tool"
    
    try:
        drones = requests.post(base_url, json={"name": "get_drones_status"}, headers=headers).json().get("result", {})
        telemetry = requests.post(base_url, json={"name": "get_drones_telemetry", "args": {"minutes_ago": 5}}, headers=headers).json().get("result", {})
        orders = requests.post(base_url, json={"name": "get_pending_orders"}, headers=headers).json().get("result", {})
        
        return {"status": drones, "telemetry": telemetry, "orders": orders}
    except Exception as e:
        print(f"[!] Errore recupero stato globale: {e}")
        return None
    
def calculate_state_memory(state_dict):
    """
    Crea impronta stato attuale con hash
    """
    state_string = json.dumps(state_dict, sort_keys=True)
    
    return hashlib.md5(state_string.encode('utf-8')).hexdigest()

def triage_manager(state_summary):
    """LLM Manager che risponde solo in JSON per instradare il lavoro."""
    prompt = f"""
    Sei il Router AI del sistema droni. Analizza questo stato e decidi chi deve intervenire.
    RISPONDI SOLO CON UN JSON VALIDO CON QUESTA STRUTTURA:
    {{"run_health": boolean, "run_logistic": boolean, "reason": "breve motivazione"}}

    REGOLE:
    - run_health = true SE ci sono droni in manutenzione, OPPURE SE ci sono ordini pendenti ma nessun drone disponibile (droni_idle_disponibili == 0) per scalare la flotta.
    - run_logistic = true SE ci sono ordini in sospeso (ordini_pendenti > 0) E ci sono droni disponibili per volare (droni_idle_disponibili > 0).
    
    STATO ATTUALE:
    {json.dumps(state_summary, indent=2)}
    """
    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} 
        )

        usage = response.usage
        print(f" [Costo Triage] Prompt: {usage.prompt_tokens} | Completamento: {usage.completion_tokens} | Totale: {usage.total_tokens}")

        decision = json.loads(response.choices[0].message.content)
        return decision
    except Exception as e:
        print(f"Errore nel Manager Triage: {e}")
        return {"run_health": True, "run_logistic": True, "reason": "Fallback: run both"}

def run_agent_loop():
    print(" --- AVVIO AI BRAIN --- ")

    last_state_mem = None
    
    while True:
        print("\n[1] Snapshot Sistema...")
        global_state = fetch_global_state()
        if not global_state:
            time.sleep(10)
            continue
   
        telemetry_data = global_state['telemetry'].get('drones_status', {})
        
        #Conta quanti droni sono effettivamente in stato IDLE
        idle_drones = sum(1 for d in telemetry_data.values() if d.get('state') == 'IDLE')

        summary = {
            "droni_totali_k8s": global_state['status'].get('total_active_drones', 0),
            "droni_idle_disponibili": idle_drones,
            "ordini_pendenti": global_state['orders'].get('total_pending', 0),
            "droni_in_manutenzione": global_state['telemetry'].get('maintenance_count', 0)
        }

        current_mem = calculate_state_memory(summary)
        
        if current_mem == last_state_mem:
            print(" Nessun cambiamento rilevato nello stato.")
            time.sleep(10)  
            continue        
            
        #hash diverso. 
        last_state_mem = current_mem
        
        print("[2] Triage Manager in corso...")
        decision = triage_manager(summary)
        print(f" -> Decisione: {decision}")


        full_order_list = global_state['orders'].get('orders', [])

        orders_available = full_order_list[:idle_drones] if idle_drones > 0 else [] 

        ready_drones = {id_drone: data for id_drone, data in telemetry_data.items() if data.get('state') == 'IDLE'}


        #Context per l'Health Agent: Gli diamo tutta la telemetria per trovare i guasti. 
        #Gli passiamo solo il numero degli ordini
        health_context = (
            f"DATI SALUTE FLOTTA:\n"
            f"- Telemetria Completa: {json.dumps(telemetry_data)}\n"
            f"- Ordini in attesa totali: {summary['ordini_pendenti']} (Usa questo dato se devi decidere uno scale-up)"
        )

        # Context per il Logistic Agent: Gli diamo SOLO i droni liberi e SOLO gli ordini che può gestire ora.
        logistic_context = (
            f"DATI LOGISTICA:\n"
            f"- Droni Disponibili (IDLE): {json.dumps(ready_drones)}\n"
            f"- Ordini da Assegnare in questo ciclo: {json.dumps(orders_available)}"
        )

        # injected_context = f"DATI AGGIORNATI:\n- Telemetria: {json.dumps(global_state['telemetry'].get('drones_status'))}\n- Ordini: {json.dumps(global_state['orders'].get('orders'))}"

        threads = []
        
        if decision.get("run_health"):
            t1 = threading.Thread(target=health_agent.run, args=(health_context,))
            threads.append(t1)
            t1.start()
            
        if decision.get("run_logistic"):
            t2 = threading.Thread(target=logistic_agent.run, args=(logistic_context,))
            threads.append(t2)
            t2.start()

        for t in threads:
            t.join()
            
        time.sleep(20)

if __name__ == "__main__":
    run_agent_loop()