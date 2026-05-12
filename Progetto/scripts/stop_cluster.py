#!/usr/bin/env python3

import os
import signal
import subprocess

def run_command(command, allow_failure=False):
    """Esegue un comando shell e gestisce gli errori."""
    print(f" Esecuzione: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        if not allow_failure:
            print(f" Errore durante l'esecuzione: {command}")
        else:
            print(f"️ Avviso ignorato durante: {command}")


def kill_agent_processes():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    pid_file = os.path.join(project_root, 'agent_pids.txt')

    if os.path.exists(pid_file):
        print(" Arresto dei processi agent registrati...")
        with open(pid_file, 'r') as f:
            for line in f:
                try:
                    pid = int(line.strip())
                    os.kill(pid, signal.SIGTERM)
                    print(f"   Process {pid} terminato")
                except Exception:
                    pass
        try:
            os.remove(pid_file)
        except Exception:
            pass
    else:
        print("ℹ️ Nessun PID file agent trovato; uso pkill come fallback.")
        run_command('pkill -f mcp_server.py', allow_failure=True)
        run_command('pkill -f logistic_ai_brain.py', allow_failure=True)

def main():
    print(" --- SPEGNIMENTO AMBIENTE BETA (DRONE SYSTEM) --- \n")

    # 0. Arresto dei processi agent locali
    print("0️⃣ Arresto dei processi MCP/AI locali...")
    kill_agent_processes()

    # 1. Distruzione del cluster
    print("1️⃣ Distruzione del cluster Kubernetes e relativi Pod...")
    run_command("kind delete cluster --name beta-drone-cluster", allow_failure=True)

    # 2. Rimozione di eventuali port-forward residui (se mai usati per debug o AI locali)
    print("\n2️⃣ Pulizia dei processi pendenti come port-forward...")
    run_command('pkill -f "kubectl port-forward"', allow_failure=True)
    
    # 3. Spegnimento di Docker
    print("\n3️⃣ Spegnimento del motore Docker (richiede sudo, puoi interrompere se vuoi lasciarlo attivo)...")
    try:
        subprocess.run("sudo systemctl stop docker", shell=True)
    except Exception:
        pass

    print("\n AMBIENTE BETA TERMINATO. Risorse di sistema liberate con successo.")

if __name__ == "__main__":
    main()