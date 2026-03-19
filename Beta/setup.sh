#!/bin/bash
# setup.sh - Script di automazione per il provisioning rapido del progetto
# Scalable and Reliable Systems

set -e

echo "=========================================="
echo " Inizializzazione Ambiente SRS Cluster k3d"
echo "=========================================="

echo "[0/6] Pulizia dell'ambiente (se un cluster esistente è presente)..."
k3d cluster delete srs-cluster || true

echo "[1/6] Bootstrapping del cluster k3d... (1 Master, 2 Agents)"
k3d cluster create --config cluster-config.yaml

echo "[2/6] Build delle immagini dei microservizi..."
docker build -f src/custom-broker/Dockerfile -t custom-broker:latest src/custom-broker
docker build -f src/order-streamer/Dockerfile -t order-streamer:latest src/order-streamer
docker build -f src/sales-agent/Dockerfile -t sales-agent:latest src/sales-agent
docker build -f src/drone-fleet/Dockerfile -t drone-fleet:latest src/drone-fleet
docker build -f src/fleet-agent/Dockerfile -t fleet-agent:latest src/fleet-agent

echo "[3/6] Import delle immagini in k3d (Critico)..."
k3d image import custom-broker:latest -c srs-cluster
k3d image import order-streamer:latest -c srs-cluster
k3d image import sales-agent:latest -c srs-cluster
k3d image import drone-fleet:latest -c srs-cluster
k3d image import fleet-agent:latest -c srs-cluster

echo "[4/6] Applicazione dei manifesti Kubernetes in /k8s..."
kubectl apply -f k8s/

echo "[5/6] Attesa che i Pod siano pronti (Liveness/Readiness)..."
kubectl rollout status deployment/custom-broker-deployment --timeout=120s
kubectl rollout status deployment/redis-deployment --timeout=120s
kubectl rollout status deployment/order-streamer-deployment --timeout=120s
kubectl rollout status deployment/sales-agent-deployment --timeout=120s
kubectl rollout status deployment/drone-fleet-deployment --timeout=120s
kubectl rollout status deployment/fleet-agent-deployment --timeout=120s

echo "[6/6] Deploy completato con successo."
echo "Usa: kubectl get pods"
echo "Log Custom Broker: kubectl logs -l app=custom-broker -f"
echo "Log Fleet AI: kubectl logs -l app=fleet-agent -f"
