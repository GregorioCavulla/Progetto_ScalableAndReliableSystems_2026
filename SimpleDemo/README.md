# SimpleDemo

Demo locale minimale per capire il flusso events -> MCP -> agent (con o senza LLM).

1. `data_streamer.py` genera log JSON randomici (JSONL).
2. `mcp_layer.py` espone un micro-layer MCP con 3 metodi pubblici:
   - `get_recent_events(...)`
   - `get_system_status(...)`
   - `run_remediation(...)`
3. `agent_demo.py` usa il layer MCP e applica regole fisse per decidere una remediation simulata.

## Esecuzione

Genera 40 eventi:

```bash
python3 data_streamer.py --count 40 --interval 0.05 --seed 7 > events.jsonl
```

Esegui l'agent:

```bash
python3 agent_demo.py --events-file events.jsonl
```

Output atteso: un JSON con stato aggregato (`healthy` / `degraded` / `critical`), eventuali errori recenti e azione scelta.

## Dashboard Locale

Puoi visualizzare tutto in una dashboard web locale (stato, eventi recenti, errori, decisione agente, trace tool MCP).

Avvio dashboard senza LLM (solo osservabilita):

```bash
python3 dashboard.py --events-file events.jsonl
```

Avvio dashboard con agente LLM (Ollama):

```bash
OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
python3 dashboard.py --events-file events.jsonl --with-agent --model qwen2.5:7b-instruct
```

Apri il browser su `http://127.0.0.1:8080`.

Se la card `Agent Final Decision` mostra `escalate_to_human`, usa i pulsanti nella sezione `Human In The Loop`:
- `Approve remediation`: esegue manualmente `run_remediation()`
- `Ignore / keep escalated`: lascia il caso in escalation umana

Per avere aggiornamenti continui, lascia uno streamer in append sul file eventi:

```bash
python3 data_streamer.py --count 100000 --interval 0.2 >> events.jsonl
```

## Mini Demo Dominio Progetto (Drone Logistics)

Per simulare il dominio del progetto, usa il profilo `drone` nello streamer.

1. Genera eventi dominio droni:

```bash
python3 data_streamer.py --profile drone --count 120 --interval 0.1 --seed 7 > events_drone.jsonl
```

2. Avvia dashboard con agente Ollama:

```bash
OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
python3 dashboard.py --events-file events_drone.jsonl --with-agent --model qwen2.5:7b-instruct
```

3. Apri `http://127.0.0.1:8080` e mostra:
- card health/error ratio
- eventi con `drone_id` e `order_id`
- decisione agente
- trace tool MCP
- approvazione umana via pulsanti `Human In The Loop`

Per una demo live continua in dominio droni:

```bash
python3 data_streamer.py --profile drone --count 100000 --interval 0.2 >> events_drone.jsonl
```
