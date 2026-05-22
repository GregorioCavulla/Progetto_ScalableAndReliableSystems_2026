#!/bin/bash
set -e

echo "========================================="
echo "   Inizializzazione Cluster Kubernetes   "
echo "========================================="

echo "1. Creazione cluster KIND per il test..."
# Non eliminiamo il cluster a priori se esiste, verifichiamo prima
if kind get clusters | grep -q "kind"; then
    echo " -> Cluster 'kind' già esistente. Se vuoi ricrearlo usa teardown_cluster.sh"
else
    kind create cluster --config cluster.yaml
fi

echo "2. Build dell'immagine Docker per Progetto_Final..."
docker build -t progetto-final-image:latest .
echo " -> Caricamento immagine su KIND..."
kind load docker-image progetto-final-image:latest

echo "3. Applico le configurazioni Kubernetes (Secrets, InfluxDB, Mosquitto)..."
kubectl apply -f configs/secrets.yaml
kubectl apply -f configs/influxdb.yaml
kubectl apply -f configs/mosquitto.yaml

echo "4. Applico i carichi di lavoro (Central Server, Drone, Client)..."
kubectl apply -f configs/central-server.yaml
kubectl apply -f configs/drone.yaml
kubectl apply -f configs/client.yaml

echo "5. Attesa (polling) che i pod core siano running..."
kubectl wait --for=condition=ready pod -l app=influxdb --timeout=120s
kubectl wait --for=condition=ready pod -l app=central-server --timeout=120s
kubectl wait --for=condition=ready pod -l app=mosquitto --timeout=120s


echo "========================================="
echo " Cluster operativo e pronto per i test!  "
echo " (Puoi monitorarlo con: kubectl get pods)"
echo "========================================="
