# MCP Agentic Operations Layer

Questa cartella contiene i due server Model Context Protocol (MCP) richiesti dall'architettura del progetto SRS.

## Architettura dei Ruoli Agentici

Rispondendo ai requisiti del progetto, le responsabilita' agentiche sono divise in **due ruoli distinti** esposti tramite server indipendenti (Least Privilege):

1. **Observability Agent Server** (`mcp_observability.py`):
   - Ruolo: Telemetria, triage, ispezione stato cluster e broker.
   - Accesso: Read-only (Non necessita di human-in-the-loop).
   - Tool: Analisi code Redis, lettura stato pod Kubernetes, diagnostica di stream logistici (droni).

2. **Remediation Agent Server** (`mcp_remediation.py`):
   - Ruolo: Rollout, scaling, recovery.
   - Guardrail di Budget: Hard-limit a un massimo di 5 repliche di picco per preservare l'OPEX e aderire al tetto dei costi previsti.
   - Guardrail di Sicurezza: Le operazioni di *emergency restart* necessitano di `human_approval_granted` a monte. Il LLM che usa questo strumento non tentera' riavvi in modo speculativo ma blocchera' il flow chiedendo conferma al professore/studente prima del commit dell'azione.

## Come usarli / testarli

1. Installare le dipendenze: `pip install -r requirements.txt`
2. Essendo server basati su I/O Standard, possono essere forniti a qualsiasi client Agent moderno (es. Claude Desktop o SDK MCP personalizzati) referenziando l'interprete Python verso questi file.

Esempio di operazione di Demo per il professore:
- **Test Stress:** Il prof killa la coda RabbitMQ.
- L'agente sfrutta *Observability* per capire che i container *order-streamer* sono andati in `CrashLoopBackOff`.
- L'agente tenta di scalare la rete, ma impatta il *Budget Limit Guardrail*.
- L'agente chiede in chat conferma via policy per eseguire un *emergency_restart_pod*.
