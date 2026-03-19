# Piano di Battaglia - Da Beta a Conformita 100% (Project SRS)

## 1) Obiettivo del piano
Portare il progetto `Beta` alla conformita completa rispetto alla consegna del professore (Project SRS), coprendo:
- requisiti funzionali del servizio distribuito
- requisiti non funzionali (scalabilita, affidabilita, osservabilita)
- requisiti agentici MCP (ruoli, guardrail, safety policy)
- deliverable documentali obbligatori (report tecnico + analisi economica/ROI)
- demo robusta sotto stress test con evidenze misurabili

## 2) Definizione di "100% conforme"
Il progetto e considerato 100% conforme solo se tutti i seguenti blocchi risultano completi e verificati:
1. Servizio distribuito containerizzato, architettura coerente con workload e failure scenario.
2. Meccanismi affidabilita/scalabilita implementati e giustificati (non solo dichiarati).
3. Observability completa (metriche, log, dashboard) con tracing decisionale durante incident.
4. Almeno 2 responsabilita agentiche distinte esposte via MCP, con confini chiari.
5. Safety policy esplicita e implementata (human approval, audit, limiti, fallback, anti-loop).
6. Failure experiments documentati e ripetibili con risultati attesi/osservati.
7. Sezione economica completa: SLO, downtime cost, OPEX/CAPEX, cost ceiling agent, trade-off, ROA.
8. Deliverable finali coerenti: codice + deploy + report tecnico + script demo + evidenze.

## 3) Gap attuali (stato iniziale)

### 3.1 Gap funzionali/architetturali critici
- Incoerenza queue ordini:
  - `order-streamer` pubblica su `orders`
  - `sales-agent` consuma da `orders.incoming`
- Rischio: pipeline ordini non end-to-end, comportamento non affidabile in demo.

### 3.2 Gap affidabilita
- Broker custom in memoria (struttura dict/list), senza persistenza reale su disco, ack esplicito, retry policy robusta.
- README dichiara concetti di durable/ack non realmente implementati nel broker corrente.

### 3.3 Gap safety/guardrail
- Presenti guardrail base (max repliche, human approval su restart).
- Mancanti o deboli:
  - anti-loop/costo inferenza con soglia tecnica concreta
  - validazione anti-hallucination prima di azioni ad alto impatto
  - rollback policy strutturata con runbook
  - audit trail persistente e verificabile

### 3.4 Gap documentali obbligatori
- Assente un report tecnico unico con tutte le sezioni richieste dal PDF/TXT.
- Assente analisi economica strutturata (SLO, downtime, costi, trade-off, ROA).
- Failure experiments non formalizzati con metodologia e risultati.

## 4) Strategia generale (ordine di esecuzione)
Approccio in 5 ondate:
1. Stabilizzazione pipeline core (funzionalita e coerenza).
2. Hardening affidabilita + osservabilita.
3. Chiusura guardrail MCP e policy safety end-to-end.
4. Failure campaign (stress test, misure, correzioni).
5. Produzione deliverable finali (report, dashboard evidenze, script demo).

## 5) Piano operativo dettagliato

## Fase A - Stabilizzazione funzionale (Priorita P0)
Obiettivo: garantire che il servizio funzioni in modo coerente e dimostrabile.

### A1. Allineamento code e naming eventi
- Azione:
  - Definire naming contract ufficiale delle queue (es. `orders.incoming`, `orders.urgent`, `orders.normal`, `drone.events`).
  - Allineare producer/consumer per evitare mismatch.
- Output:
  - Documento "Event Contract" in markdown.
  - Codice allineato in tutti i servizi.
- Acceptance:
  - Test E2E: 100 ordini generati -> 100 ordini processati senza drop da mismatch.

### A2. Validazione payload e schema
- Azione:
  - Definire schema XML ordini e JSON telemetria.
  - Validare input lato consumer (reject safe + log strutturato).
- Output:
  - Modulo di validazione condiviso.
  - Error handling su malformed requests.
- Acceptance:
  - Invio payload malformato non causa crash; evento marcato come errore e tracciato.

### A3. Idempotenza minima consumer
- Azione:
  - Introdurre idempotency key (order_id/event_id) per evitare doppia elaborazione su retry.
- Output:
  - Store temporaneo dedup (Redis set con TTL).
- Acceptance:
  - Replay dello stesso evento non genera doppie azioni business.

## Fase B - Affidabilita e scalabilita reale (Priorita P0/P1)
Obiettivo: allineare implementazione ai requisiti di reliability sotto guasto.

### B1. Evoluzione broker (scelta architetturale)
- Opzione consigliata per conformita forte:
  - Sostituire il custom broker in-memory con RabbitMQ ufficiale (durable queues + ack + DLQ).
- Opzione alternativa:
  - Mantenere custom broker ma implementare persistenza, ack state machine, retry + dead-letter (piu costoso e rischioso).
- Output:
  - Decision Record (ADR) con motivazione tecnica ed economica.
- Acceptance:
  - Riavvio broker non comporta perdita messaggi in coda durable.

### B2. Retry/backoff/timeout policy
- Azione:
  - Standardizzare timeout HTTP, retry esponenziale con jitter, max attempts, circuit breaker light.
- Output:
  - Config centralizzata per politiche di resilienza.
- Acceptance:
  - In presenza di dipendenza down, il servizio degrada senza saturare CPU/log.

### B3. Graceful degradation
- Azione:
  - Definire modalita degradate quando Redis/Broker non disponibili.
  - Ridurre funzionalita non critiche mantenendo flusso minimo operativo.
- Output:
  - Tabella "Componente down -> comportamento previsto".
- Acceptance:
  - Durante failure primaria, almeno il 1 servizio core resta operativo (partial functionality).

### B4. Scalabilita controllata
- Azione:
  - Definire regole scaling (manuale + eventuale HPA), limiti budget, soglie queue lag.
- Output:
  - Policy scaling nel report + config deployment.
- Acceptance:
  - Scale-out migliora throughput senza violare budget cap definito.

## Fase C - Observability e auditabilita (Priorita P0)
Obiettivo: rendere diagnosi, triage e post-mortem oggettivi.

### C1. Logging strutturato
- Azione:
  - Passare a log JSON con campi standard (`timestamp`, `service`, `event_id`, `queue`, `action`, `result`, `error_code`).
- Output:
  - Logging guidelines + libreria utility comune.
- Acceptance:
  - Da un incidente si ricostruisce la catena decisionale in < 10 minuti.

### C2. Metriche tecniche minime
- Azione:
  - Esportare metriche: queue depth, processing latency, error rate, restart count, agent actions count.
- Output:
  - Endpoint metrics o collector equivalente.
- Acceptance:
  - Dashboard mostra trend live e storico minimo del test.

### C3. Dashboard operativa estesa
- Azione:
  - Integrare vista lock sicurezza, azioni agent, esiti remediation, budget usage.
- Output:
  - Dashboard unica per demo e audit.
- Acceptance:
  - Operatore vede stato sistema + motivo blocco azione ad alto impatto.

### C4. Audit trail persistente
- Azione:
  - Ogni azione ad alto impatto (scale/restart) deve creare record persistente (file append-only o DB).
- Output:
  - Registro con chi/quando/perche/output tool.
- Acceptance:
  - Il docente puo verificare retrospettivamente ogni azione critica.

## Fase D - MCP Agent Layer e Safety Policy (Priorita P0)
Obiettivo: chiudere i requisiti agentici e le guardie anti-rischio.

### D1. Ruoli agentici formalizzati
- Azione:
  - Documentare chiaramente confine tra:
    - deterministic automation
    - decisione agentica
    - human-in-the-loop
- Output:
  - Tabella RACI operativa per azioni comuni/incidente.
- Acceptance:
  - Nessuna ambiguita su "chi decide" e "chi esegue".

### D2. Least privilege effettivo
- Azione:
  - Observability MCP read-only; remediation MCP write-bounded.
  - Bloccare tool non necessari ad alto rischio.
- Output:
  - Matrice permessi tool MCP.
- Acceptance:
  - Impossibile eseguire comandi distruttivi fuori policy.

### D3. Human approval workflow robusto
- Azione:
  - Rendere obbligatorio un token/flag di approvazione con TTL breve per azioni distruttive.
  - Mostrare stato approvazione in dashboard.
- Output:
  - Workflow approvazione documentato e testato.
- Acceptance:
  - Chiamate senza approvazione risultano sempre bloccate e loggate.

### D4. Anti-loop ed economic guardrails
- Azione:
  - Impostare soglie hard:
    - max tool steps per incidente
    - max tempo decisionale
    - max costo stimato inferenza/sessione
- Output:
  - Config guardrail e regole escalation automatica.
- Acceptance:
  - Superata soglia -> stop agent + escalation umana + audit event.

### D5. Hallucination/validation controls
- Azione:
  - Prima di remediation sensibile: dry-run o policy-check + consistency check su telemetria.
- Output:
  - Pipeline `propose -> validate -> approve -> execute -> verify`.
- Acceptance:
  - Nessuna azione high-impact eseguita senza validazione positiva.

### D6. Rollback e fallback policy
- Azione:
  - Definire rollback per ogni remediation (es. scala giu, rollback deployment, restore config).
- Output:
  - Runbook incident response con piani A/B/C.
- Acceptance:
  - Ogni azione ad alto impatto ha rollback documentato e testato.

## Fase E - Failure experiments e stress scenario (Priorita P0)
Obiettivo: dimostrare comportamento sotto condizioni degradate reali.

### E1. Catalogo esperimenti obbligatori
Eseguire e documentare almeno:
1. crash di un microservizio critico
2. indisponibilita Redis
3. indisponibilita broker
4. malformed requests
5. queue congestion
6. degradazione rete o timeout elevati

Per ogni esperimento:
- ipotesi
- setup
- metrica osservata
- comportamento atteso
- risultato ottenuto
- azione correttiva

### E2. Metriche di esito
- Misurare almeno:
  - MTTD (detection)
  - MTTA (acknowledgment)
  - RTO (recovery)
  - errore % durante test
- Acceptance:
  - RTO entro target dichiarato nel report.

## Fase F - Analisi economica e ROA (Priorita P0)
Obiettivo: coprire integralmente la sezione business/ROI richiesta.

### F1. SLO formali
- Definire SLO minimi (esempio):
  - Availability: 99.5% su servizio core
  - P95 processing latency ordini: < X s
  - Alerting delay: < Y s

### F2. Cost model
- Calcolare:
  - costo 1h downtime
  - costo operativo mensile (infra + tool + manutenzione)
  - ceiling costo agentico mensile
  - 1 investimento di resilienza giustificato

### F3. Trade-off obbligatori
- Scrivere in modo esplicito:
  - 1 trade-off costo vs affidabilita
  - 1 trade-off automazione vs safety

### F4. ROA (Return on Agent)
- Valutare benefici misurabili:
  - riduzione MTTD/MTTR
  - riduzione interventi manuali
  - riduzione impatto downtime
- Includere CAPEX/OPEX stimati e periodo payback indicativo.

## Fase G - Deliverable finali e demo (Priorita P0)
Obiettivo: pacchetto consegna completo, chiaro, difendibile all orale.

### G1. Struttura deliverable consigliata
Creare in `Beta/docs/`:
- `01-service-definition.md`
- `02-architecture-and-nfr.md`
- `03-reliability-and-scalability.md`
- `04-observability.md`
- `05-agent-roles-and-mcp.md`
- `06-operational-safety-policy.md`
- `07-failure-experiments.md`
- `08-cost-slo-roa.md`
- `09-devsecops-choices.md`
- `10-demo-script.md`

### G2. Demo script da 12-15 minuti
Sequenza raccomandata:
1. baseline healthy
2. stress/failure injection
3. rilevamento observability
4. proposta agentica
5. blocco guardrail/human approval
6. remediation controllata
7. recovery e verifica SLO
8. chiusura con costo/ROI

### G3. Artefatti da mostrare live
- dashboard live
- log strutturati
- audit trail azioni high-impact
- evidenza blocco policy quando richiesta non sicura

## 6) Pianificazione temporale proposta (2 settimane)

### Settimana 1
- Giorno 1-2: Fase A (coerenza pipeline, schema, idempotenza)
- Giorno 3-4: Fase B (broker decision + retry/backoff + degradation)
- Giorno 5: Fase C (logging + metriche base + audit trail)

### Settimana 2
- Giorno 1-2: Fase D (guardrail completi MCP + validation workflow)
- Giorno 3: Fase E (failure campaign e tuning)
- Giorno 4: Fase F (SLO/costi/ROA)
- Giorno 5: Fase G (report, prova demo, rifiniture finali)

## 7) Rischi principali e mitigazioni
- Rischio: migrazione broker lunga.
  - Mitigazione: ADR rapido + POC in 1 giorno + fallback piano B.
- Rischio: metriche incomplete per RTO.
  - Mitigazione: introdurre instrumentation minima obbligatoria prima degli esperimenti.
- Rischio: guardrail non dimostrabili in demo.
  - Mitigazione: test scriptato con casi positivi e casi bloccati.
- Rischio: analisi costi poco credibile.
  - Mitigazione: usare assunzioni esplicite e formule semplici, verificabili.

## 8) Definition of Done (DoD) finale
Il progetto e "ready for submission" solo se:
1. Tutti i test scenario di failure passano con risultati documentati.
2. Tutti i requisiti MCP/safety risultano implementati e dimostrabili.
3. Le sezioni economiche (SLO/costi/ROA) sono complete con numeri e assunzioni.
4. Tutti i gap P0 sono chiusi.
5. Demo script eseguibile end-to-end senza passaggi manuali ambigui.

---

# Checklist Completa (Spuntabile)

## A. Core Service
- [ ] Definito e documentato Event Contract univoco per tutte le queue.
- [ ] Allineati producer/consumer sui nomi queue (fix mismatch ordini).
- [ ] Implementata validazione schema XML ordini.
- [ ] Implementata validazione schema JSON telemetria.
- [ ] Gestione malformed payload con reject safe + log.
- [ ] Implementata idempotenza consumer con key + TTL.

## B. Reliability & Scalability
- [ ] Scelta broker formalizzata in ADR (RabbitMQ consigliato).
- [ ] Queue durable configurate (se RabbitMQ).
- [ ] Ack/negative-ack implementati (se RabbitMQ).
- [ ] Retry policy con backoff esponenziale + jitter.
- [ ] Timeout standardizzati su tutte le chiamate interne.
- [ ] Dead-letter strategy definita per eventi falliti.
- [ ] Graceful degradation documentata per dependency down.
- [ ] Policy di scaling definita con limiti economici.

## C. Kubernetes/Deploy
- [ ] Deployment aggiornati con env coerenti al nuovo contract.
- [ ] Probe health verificate su tutti i servizi.
- [ ] Resources requests/limits riviste e motivate.
- [ ] Script setup idempotente e ripetibile.
- [ ] Rollout/rollback testati almeno una volta.

## D. Observability
- [ ] Logging strutturato JSON uniforme su tutti i servizi.
- [ ] Correlation ID / event ID propagato cross-service.
- [ ] Metriche chiave esposte (queue depth, latency, error rate).
- [ ] Dashboard operativa aggiornata con stato code/sicurezza.
- [ ] Registro audit persistente per azioni ad alto impatto.

## E. MCP & Agentic Layer
- [ ] Due capability group MCP separati e documentati.
- [ ] Observability tools effettivamente read-only.
- [ ] Remediation tools bounded e policy-enforced.
- [ ] Human approval obbligatoria su azioni distruttive.
- [ ] Stato lock/approval visibile su dashboard.
- [ ] Guardrail anti-loop definiti (step/time/cost threshold).
- [ ] Guardrail economici con tetto costo/scala documentato.
- [ ] Validazione pre-azione ad alto impatto (dry-run/policy check).
- [ ] Rollback per ogni remediation ad alto rischio.

## F. Safety Policy (Documento)
- [ ] Documento esplicito con azioni auto/advisory/human approval.
- [ ] Least privilege motivato per ogni tool MCP.
- [ ] Confini di azione e rate limits definiti.
- [ ] Regole escalation in caso ambiguo chiarite.
- [ ] Regole anti-hallucination esplicitate.

## G. Failure Experiments
- [ ] Test crash servizio critico eseguito e documentato.
- [ ] Test Redis down eseguito e documentato.
- [ ] Test broker down eseguito e documentato.
- [ ] Test malformed requests eseguito e documentato.
- [ ] Test queue congestion eseguito e documentato.
- [ ] Test network degradation/timeout eseguito e documentato.
- [ ] MTTD, MTTA, RTO misurati e riportati.

## H. Economic Analysis & ROA
- [ ] SLO formali definiti e motivati.
- [ ] Costo 1h downtime stimato.
- [ ] OPEX mensile stimato.
- [ ] CAPEX principali stimati.
- [ ] Agent cost ceiling mensile definito.
- [ ] Trade-off costo/affidabilita esplicitato.
- [ ] Trade-off automazione/safety esplicitato.
- [ ] ROA con benefici misurabili e limiti dichiarati.

## I. Deliverable Finali
- [ ] Report tecnico completo con tutte le sezioni richieste.
- [ ] Architettura e MCP design chiaramente documentati.
- [ ] DevSecOps choices documentate.
- [ ] Demo script finale pronto e provato.
- [ ] Repository pulito, istruzioni run riproducibili.
- [ ] Evidenze (log, metriche, screenshot, output test) raccolte.

## J. Prova Generale (Go/No-Go)
- [ ] Dry run demo completo entro tempo target.
- [ ] Simulazione "professore ostile/confuso" passata.
- [ ] Nessuna azione high-impact eseguibile senza approvazione.
- [ ] Tutti i requisiti della consegna mappati a evidenze concrete.
- [ ] Decisione finale: GO alla consegna.
