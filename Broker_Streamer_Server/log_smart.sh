#!/bin/bash

echo "📡 In ascolto sui log dei Sensori Smart (Gruppo B)..."
echo "🛑 Premi Ctrl+C per interrompere la lettura."
echo "---------------------------------------------------"

# Usiamo max-log-requests=10 per evitare errori se fai riavvii o scali i pod
kubectl logs -f -l app=sensore-b --max-log-requests=10