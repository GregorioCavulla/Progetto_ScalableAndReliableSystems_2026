# DroneV1 Operational Safety Policy

## Scope
Questa policy regola cosa possono osservare e fare gli agenti in DroneV1.

## Agent Roles
- ObserverAgent: sola osservazione, triage e raccomandazioni.
- RemediationAgent: azioni operative limitate e validate.

## Action Classes
- Fully automated:
  - `assign_order`
  - `send_to_charge`
  - `send_to_repair` (solo se `validate_action` consente)
- Advisory only:
  - suggerimenti di dispatch e analisi rischio
- Human approval required:
  - `add_drone`
  - `abort_order`
  - `checkpoint_drop`

## Guardrails
- Least privilege:
  - ObserverAgent usa solo MCP Observability (read-only).
  - RemediationAgent usa MCP Operations con token dedicato.
- Validation before execution:
  - ogni azione passa da `validate_action`.
- Economic guardrail:
  - costo stimato agente per run <= `agent_cost_ceiling_eur`.
  - superata la soglia -> escalation automatica.
- Loop control:
  - max step Observer e Remediation configurabili.
- Idempotency:
  - `assign_order` evita doppia assegnazione identica (`idempotent_noop`).
- Auditability:
  - tutte le azioni operative e high-impact sono loggate in `data/fleet_actions.jsonl`.

## Escalation Rules
In caso di ambiguita o rischio:
- non eseguire azioni speculative;
- aprire `request_human_approval`;
- mantenere il sistema in stato reversibile.

## Rollback / Safe Fallback
- Se validazione fallisce: azione bloccata.
- Se budget superato: nessuna azione ulteriore, escalation.
- Se MCP operations non disponibile: observer-only mode, nessuna write operation.
