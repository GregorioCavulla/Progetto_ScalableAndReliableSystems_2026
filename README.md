# Progetto_ScalableAndReliableSystems_2026

Sistema distribuito per logistica droni con layer di Agentic Operations via MCP, progettato per soddisfare i requisiti di scalabilita, affidabilita, osservabilita e safety operativa richiesti dalla consegna SRS.

## Obiettivo del progetto

Il progetto implementa un servizio in dominio transportation/logistics in cui:
- simulatori cliente generano ordini con priorita e valore economico;
- una flotta di droni simulati esegue missioni via MQTT;
- un server centrale mantiene stato operativo e dashboard;
- un orchestratore AI coordina due ruoli agentici distinti (Health + Logistic) usando tool MCP;
- azioni ad alto impatto sono bloccate da guardrail e Human-in-the-Loop.

## Scope della repository

La repository contiene piu varianti del lavoro. La versione principale e attuale e in:
- Progetto_Final

Le istruzioni di esecuzione sotto sono riferite a Progetto_Final.

## Architettura (Progetto_Final)

Componenti principali:
- Central Server: ingest MQTT, stato applicativo, persistenza InfluxDB, dashboard web.
- Drone Simulator: esecuzione missioni, telemetria, consumo batteria/usura.
- Client Simulator: generazione ordini standard o stress mode.
- MCP Server: API tool per osservabilita e remediation controllata.
- Human Approval Dashboard: approvazione/rifiuto richieste critiche.
- Logistic AI Brain: orchestratore con triage e attivazione agenti.
- Health Agent: scaling controllato e richiesta approvazioni oltre soglia.
- Logistic Agent: assegnazione missioni ai droni via comando MQTT.

Dipendenze infrastrutturali:
- Kubernetes (cluster KIND locale)
- MQTT broker (Mosquitto)
- InfluxDB 2.x

## Requisiti

Prerequisiti consigliati:
- Docker
- kind
- kubectl
- Python 3.10+

Verifica rapida:
```bash
kind version
kubectl version --client
docker --version
python3 --version
```

## Configurazione segreti

Il deploy usa un Secret Kubernetes `project-secrets` applicato da `configs/secrets.yaml`.

Chiavi richieste:
- `influx-token`
- `openai-key`
- `mcp-token`

Aggiorna `Progetto_Final/configs/secrets.yaml` con valori validi prima dell'avvio.

## Avvio rapido (Kubernetes + KIND)

Dalla root di `Progetto_Final`:

```bash
cd Progetto_Final
chmod +x ops/pullup_cluster.sh ops/teardown_cluster.sh
./ops/pullup_cluster.sh
```

Lo script:
- crea cluster kind `beta-drone-cluster`;
- builda l'immagine `progetto-final-image:latest`;
- applica secrets, Mosquitto, InfluxDB e workload applicativi;
- avvia port-forward locali.

Endpoint locali principali:
- Central Dashboard: http://localhost:5000
- Human Approval Shield: http://localhost:5002
- MCP API health: http://localhost:8101/health
- InfluxDB UI: http://localhost:8086

## Spegnimento ambiente

```bash
cd Progetto_Final
./ops/teardown_cluster.sh
```

Pulizia estesa (anche cache immagini):
```bash
./ops/teardown_cluster.sh --hard
```

## Esecuzione test di affidabilita / chaos

Suite interattiva:
```bash
cd Progetto_Final
python3 ops/chaos_test_suite.py
```

Test disponibili:
1. Outage InfluxDB e misura RTO
2. Crash Mosquitto e verifica recovery/reconnect
3. Load spike ordini e verifica comportamento di scaling
4. Run completo end-to-end

Output log:
- `Progetto_Final/chaos_test_results.log`

## Agentic Operations e MCP

Il layer MCP espone gruppi di capability coerenti con la consegna:

Osservabilita/telemetria:
- `get_drones_status`
- `get_drones_telemetry`
- `get_pending_orders`
- `check_pending_approvals`

Remediation controllata:
- `send_mqtt_command`
- `scale_drone_deployment`
- `request_human_approval`

Endpoint tool API:
- `POST /tool` su MCP server (porta 8101)
- Autenticazione via header `X-MCP-Token` per tool write-capable

## Guardrail di sicurezza operativa

Meccanismi implementati:
- Least Privilege: RBAC dedicato per componenti che interagiscono con Kubernetes.
- Policy bound: scaling autonomo solo fino a soglia (`max_drones_auto = 6`).
- Human-in-the-Loop: oltre soglia o azioni critiche -> richiesta approvazione esplicita.
- Auditability: log JSONL di azioni e approvazioni in `data/audit_actions.jsonl`.
- Anti-loop / budget guardrail: limiti di iterazione e sospensione AI su errori ripetuti MCP.
- Blocchi su azioni non sicure: comandi distruttivi non eseguiti direttamente dall'agente.

## Comandi utili operativi

```bash
# Stato pod
kubectl get pods

# Log componenti
kubectl logs -f -l app=central-server
kubectl logs -f -l app=logistic-ai-brain
kubectl logs -f deployment/mcp-server
kubectl logs -f deployment/mcp-server -c human-approval-dashboard
kubectl logs -f -l app=drone-simulator
kubectl logs -f -l app=client-simulator
```

## Note tecniche

- Il deployment e containerizzato con una singola immagine applicativa Python riusata dai workload.
- I simulatori e la dashboard sono pensati per demo controllata in ambiente locale KIND.
- Le richieste di approvazione sono persistite su file JSONL nel volume condiviso del pod MCP/Human Approval.

## Limiti attuali

- InfluxDB e Mosquitto sono deployati in configurazione semplice (single instance) orientata a demo.
- Secrets di esempio nel repository vanno sostituiti prima dell'uso reale.
- Persistenza approvazioni su file locale del pod (no storage distribuito esterno).

## Team

- Lorenzo Amorosa
- Edoardo Buttazzi
- Gregorio Cavulla
