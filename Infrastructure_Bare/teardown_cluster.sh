#!/bin/bash
set -e

echo "========================================="
echo "   Teardown Infrastruttura Kubernetes    "
echo "========================================="

# Opzionale: rimozione ordinata delle risorse prima di bruciare il cluster
# Questo permette ai pod di fare un graceful shutdown se necessario
echo "1. Rimozione dei carichi di lavoro (Deployment, Service, ecc.)..."
kubectl delete -f configs/client.yaml --ignore-not-found=true
kubectl delete -f configs/drone.yaml --ignore-not-found=true
kubectl delete -f configs/central-server.yaml --ignore-not-found=true
kubectl delete -f configs/mosquitto.yaml --ignore-not-found=true
kubectl delete -f configs/influxdb.yaml --ignore-not-found=true
kubectl delete -f configs/secrets.yaml --ignore-not-found=true

echo "2. Distruzione del cluster KIND..."
kind delete cluster

if [[ "$1" == "--hard" ]]; then
    echo "3. [HARD MODE] Pulizia dell'immagine Docker generata localmente..."
    docker rmi progetto-final-image:latest 2>/dev/null || true
    docker image prune -f
else
    echo "3. Immagine Docker mantenuta nella cache (esegui con '--hard' per rimuoverla)."
fi

echo "========================================="
echo "    Cluster spento e pulito con successo "
echo "========================================="
