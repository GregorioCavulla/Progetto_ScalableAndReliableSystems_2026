#!/bin/bash
echo "🎛️ Scegli la modalità del Pannello di Controllo:"
echo "1) Standard (Manuale)"
echo "2) Assistente AI Guidato (Groq MCP)"
read -p "Scelta [1/2]: " mode

if [ "$mode" == "2" ]; then
    echo "🧠 Teletrasporto nel Pannello Assistito dall'Intelligenza Artificiale..."
    kubectl exec -it deployment/pannello-controllo -- python ai_pannello.py
else
    echo "🔌 Teletrasporto nel Pannello di Controllo Manuale..."
    kubectl exec -it deployment/pannello-controllo -- python controller.py
fi