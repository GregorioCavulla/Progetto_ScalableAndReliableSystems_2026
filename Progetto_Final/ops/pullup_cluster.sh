#!/bin/bash
set -e

# Risali alla root del progetto: questo script vive in ops/ ma usa configs/, Dockerfile, ecc. dal parent.
cd "$(dirname "$0")/.."

CLUSTER_NAME="beta-drone-cluster"
IMAGE_NAME="progetto-final-image:latest"

echo "========================================="
echo "   Inizializzazione Cluster Kubernetes   "
echo "         (Progetto_effAgent)             "
echo "========================================="

echo "1. Creazione cluster KIND '$CLUSTER_NAME'..."
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo " -> Cluster '$CLUSTER_NAME' gia' esistente. Salto creazione (usa teardown_cluster.sh per ricrearlo)."
else
    kind create cluster --config cluster.yaml --name "$CLUSTER_NAME"
fi

echo "2. Build dell'immagine Docker $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .
echo " -> Caricamento immagine su KIND..."
kind load docker-image "$IMAGE_NAME" --name "$CLUSTER_NAME"

echo "3. Applico Secrets e infrastruttura di base (InfluxDB, Mosquitto)..."
kubectl apply -f configs/secrets.yaml
kubectl apply -f configs/influxdb.yaml
kubectl apply -f configs/mosquitto.yaml

echo "4. Applico i carichi di lavoro (Central Server, MCP, AI Brain, Drone, Client)..."
kubectl apply -f configs/mcp-server.yaml
kubectl apply -f configs/central-server.yaml
kubectl apply -f configs/ai-brain.yaml
kubectl apply -f configs/drone.yaml
kubectl apply -f configs/client.yaml

echo "5. Attesa (polling) che i pod core siano running..."
kubectl wait --for=condition=ready pod -l app=influxdb --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=mosquitto --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=mcp-server --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=central-server --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=logistic-ai-brain --timeout=120s || true

echo "6. Avvio port-forward in background (InfluxDB, MQTT, Dashboard, Approval Shield)..."
PID_FILE="agent_pids.txt"
: > "$PID_FILE"

start_pf() {
    local svc="$1"
    local mapping="$2"
    local label="$3"
    kubectl port-forward "$svc" "$mapping" >/dev/null 2>&1 &
    local pid=$!
    echo "$pid" >> "$PID_FILE"
    echo "   -> $label ($svc $mapping) PID=$pid"
}

start_pf "svc/influxdb-service"    "8086:8086" "InfluxDB"
start_pf "svc/mosquitto-service"   "1883:1883" "MQTT broker"
start_pf "deployment/central-server" "5000:5000" "Central Dashboard"
start_pf "svc/mcp-server-service"  "5002:5002" "Human Approval Shield"
start_pf "svc/mcp-server-service"  "8101:8101" "MCP API"

sleep 2  # lascia ai port-forward il tempo di aprire i socket

echo ""
echo "========================================="
echo " AMBIENTE BETA AVVIATO CON SUCCESSO!"
echo "========================================="
echo ""
echo " Dashboard & API:"
echo "   Central Dashboard ......... http://localhost:5000"
echo "   Human Approval Shield ..... http://localhost:5002"
echo "   MCP API (/health) ......... http://localhost:8101/health"
echo "   InfluxDB UI ............... http://localhost:8086"
echo ""
echo " Comandi utili:"
echo "   Stato pod:           kubectl get pods"
echo "   Log droni:           kubectl logs -f -l app=drone-simulator"
echo "   Log client:          kubectl logs -f -l app=client-simulator"
echo "   Log central-server:  kubectl logs -f -l app=central-server"
echo "   Log MCP server:      kubectl logs -f deployment/mcp-server"
echo "   Log AI Brain:        kubectl logs -f deployment/logistic-ai-brain"
echo "   Log Approval Shield: kubectl logs -f deployment/mcp-server -c human-approval"
echo ""
echo " Per spegnere tutto (cluster + port-forward): ./ops/teardown_cluster.sh"
echo "========================================="
