# DroneV1

Drone logistics demo con requisiti avanzati (esclusa containerizzazione):
- due server MCP separati (observability + operations)
- due ruoli agentici separati (ObserverAgent + RemediationAgent)
- human-in-the-loop su azioni high-impact
- guardrail economici, loop bounds, validazione azioni, audit
- failure scenarios e report tecnico base

## Struttura Principale
- `drone_streamer.py`
- `order_streamer.py`
- `mcp_layer.py`
- `mcp_observability_server.py`
- `mcp_operations_server.py`
- `observer_agent.py`
- `remediation_agent.py`
- `agent_demo.py` (coordinator)
- `dashboard.py`
- `start_demo.sh`
- `failure_scenarios.sh`
- `SAFETY_POLICY.md`
- `REPORT.md`

## Prerequisiti
```bash
ollama serve
ollama pull qwen2.5:7b-instruct
pip install openai requests
```

## Avvio Unico
```bash
cd /home/ghigo/Documenti/GitHub/Progetto_SRS_2026/DroneV1
bash start_demo.sh
```

Dashboard:
- http://127.0.0.1:8090

## Esecuzione Manuale Componenti
1. Streamers
```bash
python3 drone_streamer.py --data-dir data --ticks 100000 --interval 0.5
python3 order_streamer.py --data-dir data --count 100000 --interval 0.8
```

2. MCP servers
```bash
python3 mcp_observability_server.py --data-dir data --port 8101
python3 mcp_operations_server.py --data-dir data --port 8102 --token dronev1-token
```

3. Coordinator run singolo
```bash
OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
python3 agent_demo.py --obs-url http://127.0.0.1:8101 --ops-url http://127.0.0.1:8102 --ops-token dronev1-token --data-dir data
```

## Guardrail Chiave
- azioni high-impact (`add_drone`, `abort_order`, `checkpoint_drop`) richiedono approvazione umana
- validazione `validate_action` prima delle write operation
- costo stimato per run con ceiling configurato
- tracciamento completo in `data/fleet_actions.jsonl`

## Failure Testing
```bash
bash failure_scenarios.sh
```

## Note
- Questa versione e progettata per conformita funzionale ai requisiti agentici/safety.
- La containerizzazione e rinviata alla fase successiva.
