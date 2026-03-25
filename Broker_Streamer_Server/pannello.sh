#!/bin/bash

echo "🔌 Teletrasporto nel Pannello di Controllo in corso..."
kubectl exec -it deployment/pannello-controllo -- python controller.py