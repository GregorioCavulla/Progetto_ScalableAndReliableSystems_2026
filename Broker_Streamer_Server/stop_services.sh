#!/bin/bash

echo "🛑 --- SPEGNIMENTO LABORATORIO IOT --- 🛑"

echo "1️⃣ Distruzione del cluster Kubernetes e pulizia container..."
kind delete cluster --name lab

echo "2️⃣ Spegnimento del motore Docker..."
sudo systemctl stop docker

echo ""
echo "✅ LABORATORIO SPENTO. Risorse di sistema liberate con successo. Buonanotte!"