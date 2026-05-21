import os
import time
import json
import threading
import requests
import sys
import hashlib
from datetime import datetime
sys.stdout.reconfigure(line_buffering=True)
from openai import OpenAI
from health_agent import HealthAgent
from logistic_agent import LogisticAgent

API_BASE = "https://litellm-proxy-1013932759942.europe-west8.run.app/v1"
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = "gemini-2.5-pro"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8101")
MCP_TOKEN = os.getenv("MCP_TOKEN", "REDACTED_MCP_TOKEN")

#PROTEZIONE IN CASO DI PROBLEMI COMUNICAZIONE MCP per evitare spreco di token degli agenti
FAILURE_THRESHOLD = int(os.getenv("FAILURE_THRESHOLD", "50"))  # Numero di fallimenti consecutivi prima della sospensione
failure_counter = 0
ai_suspended = False
suspension_reason = None
suspension_time = None

health_agent = HealthAgent(API_KEY, API_BASE, MODEL_NAME, MCP_SERVER_URL, MCP_TOKEN)
logistic_agent = LogisticAgent(API_KEY, API_BASE, MODEL_NAME, MCP_SERVER_URL, MCP_TOKEN)
llm_client = OpenAI(api_key=API_KEY, base_url=API_BASE)


def fetch_global_state():
    """Recupera tutti i dati dal server MCP con chiamate HTTP."""
    global failure_counter, ai_suspended, suspension_reason, suspension_time
    
    headers = {"X-MCP-Token": MCP_TOKEN}
    base_url = f"{MCP_SERVER_URL.rstrip('/')}/tool"
    
    #Se fallisce n chiamate consecutive, sospendere llm
    try:
        drones = requests.post(base_url, json={"name": "get_drones_status"}, headers=headers, timeout=15).json().get("result", {})
        telemetry = requests.post(base_url, json={"name": "get_drones_telemetry", "args": {"minutes_ago": 5}}, headers=headers, timeout=15).json().get("result", {})
        orders = requests.post(base_url, json={"name": "get_pending_orders"}, headers=headers, timeout=15).json().get("result", {})
   
        if failure_counter > 0:
            print(f"Sistema ripristinato - Contatore azzerato (era {failure_counter})")
            failure_counter = 0
        
        return {"status": drones, "telemetry": telemetry, "orders": orders}
        
    except Exception as e:
        failure_counter += 1
        error_msg = f"Errore recupero stato globale: {e}"
        print(f"[!] {error_msg} [Tentativo {failure_counter}/{FAILURE_THRESHOLD}]")
        
        if failure_counter >= FAILURE_THRESHOLD and not ai_suspended:
            ai_suspended = True
            suspension_reason = "Fallimento comunicazione MCP"
            suspension_time = datetime.now().isoformat()
            
        return None

    
def triage_manager(summary, pending):
    decision = {"run_health": False, "run_logistic": False}
    
    if pending:
        print(" [Triage] Richiesta in attesa")
        if summary["ordini_pendenti"] > 0 and summary["droni_idle_disponibili"] > 0:
            decision["run_logistic"] = True
        return decision

    if (summary["ordini_pendenti"] > 0 and summary["droni_idle_disponibili"] == 0) or summary["droni_in_manutenzione"] > 0:
        decision["run_health"] = True
        
    if summary["ordini_pendenti"] > 0 and summary["droni_idle_disponibili"] > 0:
        decision["run_logistic"] = True
        
    return decision

def pending_approvals(mcp_url, mcp_token):
    """
    Interroga MCP per vedere se c'è una richiesta in attesa di approvazione umana. 
    """

    headers = {"X-MCP-Token": mcp_token}
    payload = {"name": "check_pending_approvals", "args": {}}
    
    try:
        resp = requests.post(f"{mcp_url}/tool", json=payload, headers=headers, timeout=5)
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            
            pending_list = result.get("pending", []) if isinstance(result, dict) else []
            
            if len(pending_list) > 0:
                return True
                
        return False
        
    except Exception as e:
        print(f" [!] Errore di rete controllo approvazioni: {e}")
        return False


def run_agent_loop():
    global ai_suspended, suspension_reason, suspension_time, failure_counter
    
    print(" --- AVVIO AI --- ")
    time.sleep(5)  #Attesa per assicurarsi che MCP sia online

    orders_a = set()
    cycle_count = 0
    
    while True:
        cycle_count += 1
        
        if ai_suspended:
            print(f"\n AI disattivata dal {suspension_time}")
            print(f" Motivo: {suspension_reason}")
            print(f" Attesa per ripristino del sistema...")
            time.sleep(60)  #Check ogni minuto se il sistema è tornato online
            continue
        
        print(f"\n[Snapshot Sistema...")
        global_state = fetch_global_state()
        if not global_state:
            time.sleep(10)
            continue
   
        telemetry_data = global_state['telemetry'].get('drones_status', {})
        
        #Conta quanti droni sono in stato IDLE
        idle_drones = sum(1 for d in telemetry_data.values() if d.get('state') == 'IDLE')

        summary = {
            "droni_totali_k8s": global_state['status'].get('total_active_drones', 0),
            "droni_idle_disponibili": idle_drones,
            "ordini_pendenti": global_state['orders'].get('total_pending', 0),
            "droni_in_manutenzione": global_state['telemetry'].get('maintenance_count', 0)
        }
               
        
        print("[2] Decisione in corso...")
        pending = pending_approvals(MCP_SERVER_URL, MCP_TOKEN)

        #block ordini

        full_order_list = [o for o in global_state['orders'].get('orders', []) if isinstance(o, dict)]
        actual_orders_ids = {o.get("order_id") for o in full_order_list if o.get("order_id")}
        orders_a.intersection_update(actual_orders_ids)

        final_orders_list = [o for o in full_order_list if o.get("order_id") not in orders_a]
        orders_available = final_orders_list[:idle_drones] if idle_drones > 0 else []

        ready_drones = {}
        for id_drone, data in telemetry_data.items():
            if data.get('state') == 'IDLE':
                batt = data.get('battery', 0)
                wear = data.get('wear', 0)
                
                max_weight = (batt - 15) / 10.0
                if wear > 20: max_weight = min(max_weight, 3.0) 
                max_weight = max(0, min(5.0, max_weight)) 
                
                ready_drones[id_drone] = {
                    "battery_percent": batt,
                    "wear_percent": wear,
                    "MAX_CAPACITY_KG": round(max_weight, 1) 
                }

        summary["ordini_pendenti"] = len(final_orders_list)
        summary["ordini_da_assegnare"] = final_orders_list

        ########################

        decision = triage_manager(summary, pending)
        print(f" -> Decisione: {decision}")


        health_context = (
            f"Droni operativi: {summary['droni_totali_k8s']}\n"
            f"Droni in manutenzione: {summary['droni_in_manutenzione']}\n"
            f"Ordini pendenti totali: {summary['ordini_pendenti']}\n"
            f"Droni IDLE disponibili: {summary['droni_idle_disponibili']}"
        )

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
            t2 = threading.Thread(target=logistic_agent.run, args=(logistic_context, orders_a))
            threads.append(t2)
            t2.start()

        for t in threads:
            t.join()
            
        time.sleep(20)

if __name__ == "__main__":
    run_agent_loop()