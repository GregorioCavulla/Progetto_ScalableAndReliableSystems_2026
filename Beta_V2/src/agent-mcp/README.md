# MCP Agentic Layer - Beta_V2

Questa cartella implementa due capability group MCP, come richiesto dalla consegna:

1. Observability MCP (`mcp_observability.py`)
2. Remediation MCP (`mcp_remediation.py`)

## 1) Distinzione dei ruoli (Least Privilege)

### Observability MCP (read-only)
Tool principali:
- `get_broker_health`
- `get_queue_snapshot`
- `get_domain_risk_assessment`
- `read_recent_remediation_audit`

Questo server non esegue azioni operative o distruttive.

### Remediation MCP (write-bounded)
Tool principali:
- `get_pending_domain_recommendations`
- `propose_domain_action`
- `approve_action`
- `execute_approved_action`
- `request_safe_fallback`
- `get_action_status`

Questo server puo proporre/eseguire solo azioni bounded e policy-checked.

## 2) Safety policy implementata

- High-impact actions richiedono approvazione umana esplicita con token e TTL.
- Azioni senza token valido o con token scaduto sono bloccate.
- Limite economico su azioni (`MCP_MAX_ESTIMATED_COST_DELTA`).
- Limite operativo anti-loop per incidente (`MCP_MAX_ACTIONS_PER_INCIDENT`).
- Limite hard su delta droni (`MCP_MAX_DRONE_DELTA`).
- Audit trail persistente append-only in JSONL (`MCP_AUDIT_LOG_PATH`).
- In caso di bassa confidenza e supportato fallback sicuro (`request_safe_fallback`).

Azioni dominio consentite (`action_type`):
- `ADD_DRONES`
- `SET_ORDER_TIMEOUT_POLICY`
- `SCHEDULE_MAINTENANCE_WINDOW`
- `ENABLE_DEGRADED_MODE`
- `REBALANCE_FLEET`

Nota: il remediation MCP non modifica deployment Kubernetes e non esegue azioni su server. Pubblica comandi dominio su `ops.domain.commands`.

## 3) Deterministico vs Agentico vs Human-in-the-loop

- Deterministico: validazione policy, check token, limiti costi/repliche, idempotenza stato azione.
- Agentico: decisione su quando proporre una remediation e su quale opzione scegliere.
- Human-in-the-loop: approvazione obbligatoria prima dell'esecuzione high-impact.

## 4) Come eseguire localmente

```bash
cd src/agent-mcp
pip install -r requirements.txt
python mcp_observability.py
# oppure
python mcp_remediation.py
```

## 5) Variabili utili

- `BROKER_HOST` (default: `custom-broker`)
- `BROKER_PORT` (default: `80`)
- `MCP_MAX_DRONE_DELTA` (default: `5`)
- `MCP_MAX_ACTIONS_PER_INCIDENT` (default: `5`)
- `MCP_MAX_ESTIMATED_COST_DELTA` (default: `250.0`)
- `MCP_MAX_APPROVAL_TTL_SECONDS` (default: `900`)
- `MCP_STATE_DIR` (default: `/tmp/mcp-remediation`)
- `MCP_AUDIT_LOG_PATH` (default: `/tmp/mcp-remediation/audit.log`)
