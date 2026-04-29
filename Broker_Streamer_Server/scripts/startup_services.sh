#!/bin/bash

# Interrompe lo script se c'è un errore grave
set -e

# Assicuriamoci di essere nella cartella corretta (root del progetto)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT" || { echo "❌ Cartella non trovata!"; exit 1; }

echo "🚀 --- INIZIALIZZAZIONE LABORATORIO IOT --- 🚀"

echo "1️⃣ Avvio del motore Docker..."
if ! systemctl is-active --quiet docker; then
    echo "Docker non attivo: avvio del demone..."
    sudo systemctl start docker
    sleep 2 # Diamo tempo al demone di svegliarsi
else
    echo "Docker già attivo."
fi

echo "2️⃣ Creazione del cluster Kubernetes (Kind) se non esiste..."
if kind get clusters | grep -q "^lab$"; then
    echo "Cluster 'lab' già presente: salto la creazione."
else
    kind create cluster --config configs/cluster.yaml --name lab
fi

echo "3️⃣ Build delle immagini Docker UFFICIALI (v1) se mancanti..."
for img in iot-streamer:v1 iot-server:v1 iot-toolbox:v1; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        echo "Immagine $img già presente, salto build."
    else
        echo "Build immagine $img..."
        docker build -t "$img" .
    fi
done

echo "4️⃣ Caricamento immagini nei nodi del cluster..."
for img in iot-streamer:v1 iot-server:v1 iot-toolbox:v1; do
    echo "Carico $img in kind (ignoro eventuali errori)..."
    kind load docker-image "$img" --name lab || true
done

echo "5️⃣ Deploy dei pilastri dell'infrastruttura (Mosquitto & InfluxDB)..."
kubectl apply -f configs/mosquitto.yaml
kubectl apply -f configs/influxdb.yaml

echo "⏳ Attesa che Broker e Database siano operativi (può richiedere un minuto)..."
sleep 5 # Pausa per far recepire i comandi a K8s
kubectl wait --for=condition=available --timeout=120s deployment/mosquitto || true
kubectl wait --for=condition=available --timeout=120s deployment/influxdb || true

echo "7️⃣ Deploy dell'Ecosistema IoT..."
kubectl apply -f configs/server.yaml
kubectl apply -f configs/streamers.yaml
kubectl apply -f configs/controller.yaml
kubectl apply -f configs/mcp.yaml

sleep 50 # Tempo per far partire tutto (incluso MCP che è un po' lento)
echo "8️⃣ Attivazione Port-Forwarding per MCP e Pannello AI (in background)..."
nohup kubectl port-forward svc/mcp-observer-service 8101:8101 > /tmp/portforward_mcp_observer.log 2>&1 &
echo $! > /tmp/portforward_mcp_observer.pid
nohup kubectl port-forward svc/mcp-operations-service 8102:8102 > /tmp/portforward_mcp_operations.log 2>&1 &
echo $! > /tmp/portforward_mcp_operations.pid
sleep 2 # Tempo per far agganciare il port forwarding

echo "9️⃣ Esecuzione del Coordinator CrewAI (Agentic System)..."
if [ -d "venv" ]; then
    echo "Ambiente virtuale trovato. L'Agent sta partendo in background..."
    source venv/bin/activate
    python iot_agent_coordinator_crew.py > agent_crew.log 2>&1 &
    AGENT_PID=$!
    echo $AGENT_PID > agent_crew.pid
else
    echo "⚠️ Ambiente virtuale non trovato. Esegui 'python3 -m venv venv' e installa le dipendenze richieste." 
fi

echo ""
echo "✅ LABORATORIO OPERATIVO AL 100%!"
echo "👉 Per vedere i log del server:  kubectl logs -f deployment/server-centrale"
echo "👉 Per vedere i log dell'Agent:  tail -f agent_crew.log"
echo "👉 Per aprire il Pannello AI:   source venv/bin/activate && python ai_pannello.py"
echo "👉 Per aprire la dashboard DB:  kubectl port-forward svc/influxdb-service 8086:8086"