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

echo "6️⃣ Deploy dell'Ecosistema IoT..."
kubectl apply -f server.yaml
kubectl apply -f streamers.yaml
kubectl apply -f controller.yaml
kubectl apply -f mcp.yaml

echo "7️⃣ Trigger manuale del primo run del Coordinator..."
kubectl create job --from=cronjob/mcp-coordinator-job mcp-coordinator-initial-run

echo ""
echo "✅ LABORATORIO OPERATIVO AL 100%!"
echo "👉 Per vedere i log del server:  kubectl logs -f deployment/server-centrale"
echo "👉 Per vedere i log dell'Agent:  kubectl logs -f job/mcp-coordinator-initial-run"
echo "👉 Per aprire la dashboard DB:  kubectl port-forward svc/influxdb-service 8086:8086"