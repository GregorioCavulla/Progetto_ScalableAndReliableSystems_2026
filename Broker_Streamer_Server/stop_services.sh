#!/bin/bash

echo "🛑 --- SPEGNIMENTO LABORATORIO IOT --- 🛑"

echo "1️⃣ Distruzione del cluster Kubernetes e pulizia container..."
kind delete cluster --name lab

<<<<<<< HEAD
echo "2️⃣ Chiusura dei processi di port-forwarding ed Agent..."
pkill -f "kubectl port-forward svc/mcp-.*" || echo "Nessun port-forwarding attivo trovato."
if [ -f "agent_crew.pid" ]; then
    kill $(cat agent_crew.pid) 2>/dev/null || echo "Processo Agent CrewAI già terminato."
    rm -f agent_crew.pid
fi
pkill -f "python iot_agent_coordinator_crew.py" || true

echo "3️⃣ Spegnimento del motore Docker..."
=======
echo "2️⃣ Spegnimento del motore Docker..."
>>>>>>> parent of e51111b (ProvineLab0)
sudo systemctl stop docker

echo ""
echo "✅ LABORATORIO SPENTO. Risorse di sistema liberate con successo. Buonanotte!"