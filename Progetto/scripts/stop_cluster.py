#!/usr/bin/env python3

import os
import subprocess

def run_command(command, allow_failure=False):
    """Esegue un comando shell e gestisce gli errori."""
    print(f"🔄 Esecuzione: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        if not allow_failure:
            print(f"❌ Errore durante l'esecuzione: {command}")
        else:
            print(f"⚠️ Avviso ignorato durante: {command}")

def main():
    print("🛑 --- SPEGNIMENTO AMBIENTE BETA (DRONE SYSTEM) --- 🛑\n")

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

    print("\n✅ AMBIENTE BETA TERMINATO. Risorse di sistema liberate con successo.")

if __name__ == "__main__":
    main()