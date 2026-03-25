#!/bin/bash
echo "🔌 Teletrasporto nel Pannello di Controllo..."
kubectl exec -it deployment/pannello-controllo -- python controller.py