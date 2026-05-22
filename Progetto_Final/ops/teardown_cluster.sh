#!/bin/bash
set -e

# Risali alla root del progetto: questo script vive in ops/ ma usa configs/ dal parent.
cd "$(dirname "$0")/.."

CLUSTER_NAME="beta-drone-cluster"
IMAGE_NAME="progetto-final-image:latest"

echo "0. Stop dei port-forward in background (se presenti)..."
if [[ -f agent_pids.txt ]]; then
    while read -r pid; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "   -> killed PID $pid"
        fi
    done < agent_pids.txt
    rm -f agent_pids.txt
fi
# fallback: ammazza eventuali kubectl port-forward orfani
pkill -f "kubectl port-forward" 2>/dev/null || true

echo "========================================="
echo "   Teardown Infrastruttura Kubernetes    "
echo "         (Progetto_effAgent)             "
echo "========================================="

echo "1. Rimozione dei carichi di lavoro (Deployment, Service, ecc.)..."
kubectl delete -f configs/client.yaml --ignore-not-found=true
kubectl delete -f configs/drone.yaml --ignore-not-found=true
kubectl delete -f configs/ai-brain.yaml --ignore-not-found=true
kubectl delete -f configs/central-server.yaml --ignore-not-found=true
kubectl delete -f configs/mcp-server.yaml --ignore-not-found=true
kubectl delete -f configs/mosquitto.yaml --ignore-not-found=true
kubectl delete -f configs/influxdb.yaml --ignore-not-found=true
kubectl delete -f configs/secrets.yaml --ignore-not-found=true

echo "2. Distruzione del cluster KIND '$CLUSTER_NAME'..."
kind delete cluster --name "$CLUSTER_NAME"

if [[ "$1" == "--hard" ]]; then
    echo "3. [HARD MODE] Pulizia dell'immagine Docker generata localmente..."
    docker rmi "$IMAGE_NAME" 2>/dev/null || true
    docker image prune -f
else
    echo "3. Immagine Docker mantenuta nella cache (esegui con '--hard' per rimuoverla)."
fi

echo "========================================="
echo "    Cluster spento e pulito con successo "
echo "========================================="
