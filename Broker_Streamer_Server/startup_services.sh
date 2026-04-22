#!/bin/bash

# Interrompe lo script se c'è un errore grave
set -e

# Assicuriamoci di essere nella cartella giusta
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || { echo "❌ Cartella non trovata!"; exit 1; }

echo "🚀 --- INIZIALIZZAZIONE LABORATORIO IOT --- 🚀"

echo "1️⃣ Avvio del motore Docker..."
sudo systemctl start docker
sleep 2 # Diamo tempo al demone di svegliarsi

echo "2️⃣ Creazione del cluster Kubernetes (Kind)..."
kind create cluster --config cluster.yaml --name lab

echo "3️⃣ Build delle immagini Docker UFFICIALI (v1)..."
docker build -t iot-streamer:v1 .
docker build -t iot-server:v1 .
docker build -t iot-toolbox:v1 .

echo "4️⃣ Caricamento immagini nei nodi del cluster..."
kind load docker-image iot-streamer:v1 --name lab
kind load docker-image iot-server:v1 --name lab
kind load docker-image iot-toolbox:v1 --name lab

echo "5️⃣ Deploy dei pilastri dell'infrastruttura (Mosquitto & InfluxDB)..."
kubectl apply -f mosquitto.yaml
kubectl apply -f influxdb.yaml

echo "⏳ Attesa che Broker e Database siano operativi (può richiedere un minuto)..."
sleep 5 # Pausa per far recepire i comandi a K8s
kubectl wait --for=condition=available --timeout=120s deployment/mosquitto
kubectl wait --for=condition=available --timeout=120s deployment/influxdb

echo "7️⃣ Deploy dell'Ecosistema IoT..."
kubectl apply -f server.yaml
kubectl apply -f streamers.yaml
kubectl apply -f controller.yaml
kubectl apply -f mcp.yaml
<<<<<<< HEAD
sleep 50 # Tempo per far partire tutto (incluso MCP che è un po' lento)
echo "8️⃣ Attivazione Port-Forwarding per MCP e Pannello AI (in background)..."
kubectl port-forward svc/mcp-observer-service 8101:8101 > /dev/null 2>&1 &
kubectl port-forward svc/mcp-operations-service 8102:8102 > /dev/null 2>&1 &
sleep 2 # Tempo per far agganciare il port forwarding

echo "9️⃣ Esecuzione del Coordinator CrewAI (Agentic System)..."
if [ -d "venv" ]; then
    echo "Ambiente virtuale trovato. L'Agent sta partendo in background..."
    source venv/bin/activate
    python iot_agent_coordinator_crew.py > agent_crew.log 2>&1 &
    AGENT_PID=$!
    echo $AGENT_PID > agent_crew.pid
else
    echo "⚠️ Ambiente virtuale non trovato. Esegui 'python3.12 -m venv venv' e installa crewai prima!"
fi
=======

echo "7️⃣ Trigger manuale del primo run del Coordinator..."
kubectl create job --from=cronjob/mcp-coordinator-job mcp-coordinator-initial-run
>>>>>>> parent of e51111b (ProvineLab0)

echo ""
echo "✅ LABORATORIO OPERATIVO AL 100%!"
echo "👉 Per vedere i log del server:  kubectl logs -f deployment/server-centrale"
echo "👉 Per vedere i log dell'Agent:  tail -f agent_crew.log"
echo "👉 Per aprire il Pannello AI:   source venv/bin/activate && python ai_pannello.py"
echo "👉 Per aprire la dashboard DB:  kubectl port-forward svc/influxdb-service 8086:8086"