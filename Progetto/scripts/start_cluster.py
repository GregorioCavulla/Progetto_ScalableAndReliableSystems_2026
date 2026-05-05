#!/usr/bin/env python3

import os
import subprocess
import sys
import time

def run_command(command, allow_failure=False, hide_output=False):
    """Esegue un comando shell e gestisce gli errori."""
    print(f"🔄 Esecuzione: {command}")
    try:
        if hide_output:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        else:
            subprocess.run(command, shell=True, check=True)
            return ""
    except subprocess.CalledProcessError as e:
        if not allow_failure:
            print(f"❌ Errore durante l'esecuzione del comando: {command}")
            if hide_output:
                print(f"Dettagli:\n{e.stderr}")
            sys.exit(1)
        return ""

def main():
    print("🚀 --- INIZIALIZZAZIONE AMBIENTE BETA (DRONE SYSTEM) --- 🚀\n")

    # 0. Entrare nella cartella corretta
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    os.chdir(project_root)
    print(f"📍 Posizionato in: {project_root}")

    # 1. Controllare se Docker è attivo
    print("\n1️⃣ Controllo stato di Docker...")
    try:
        docker_status = run_command("systemctl is-active docker", allow_failure=True, hide_output=True).strip()
        if docker_status != "active":
            print("Docker non attivo. Avvio del demone Docker (potrebbe richiedere password sudo)...")
            run_command("sudo systemctl start docker")
            time.sleep(2)
        else:
            print("Docker è già attivo.")
    except Exception as e:
        print("Impossibile verificare systemctl, assumerò che Docker sia in esecuzione.")

    # 2. Creazione del cluster Kind
    print("\n2️⃣ Creazione del cluster Kubernetes (Kind)...")
    clusters = run_command("kind get clusters", allow_failure=True, hide_output=True)
    if "beta-drone-cluster" in clusters:
        print("Cluster 'beta-drone-cluster' confermato come già esistente. Salto la creazione.")
    else:
        run_command("kind create cluster --config cluster.yaml --name beta-drone-cluster")

    # 3. Build dell'immagine Docker
    print("\n3️⃣ Compilazione dell'immagine Docker beta-drone-system:latest...")
    run_command("docker build -t beta-drone-system:latest .")

    # 4. Caricamento dell'immagine nel cluster
    print("\n4️⃣ Caricamento dell'immagine Docker all'interno dei nodi di Kind...")
    run_command("kind load docker-image beta-drone-system:latest --name beta-drone-cluster")

    # 5. Messa in opera dei file yaml su K8S
    print("\n5️⃣ Applicazione della configurazione Kubernetes (Deployments & Services)...")
    run_command("kubectl apply -f configs/")

    # 6. Wait (Opzionale: attende che il broker sia pronto)
    print("\n⏳ Attesa dei pod vitali (Mosquitto & InfluxDB)...")
    time.sleep(5) # Piccola pausa per permettere al cluster di registrare i container
    run_command("kubectl wait --for=condition=available --timeout=120s deployment/mosquitto || true", allow_failure=True)
    run_command("kubectl wait --for=condition=available --timeout=120s deployment/influxdb || true", allow_failure=True)

    print("\n✅ AMBIENTE BETA AVVIATO CON SUCCESSO!")
    print("👉 Comandi Utili:")
    print("   Visualizza i pod:          kubectl get pods")
    print("   Visualizza log droni:      kubectl logs -f -l app=drone-simulator")
    print("   Visualizza log ordini:     kubectl logs -f -l app=client-simulator")
    print("   Visualizza log server:     kubectl logs -f -l app=central-server")

if __name__ == "__main__":
    main()