# DroneDemo

Mini progetto locale nel dominio drone logistics con:
- telemetria flotta droni
- stream ordini con urgenza
- MCP layer per osservabilita e azioni
- agent LLM (Ollama) con tool-calling
- human in the loop per decisioni ad alto impatto

## Struttura

- drone_streamer.py: genera telemetria per 4 droni iniziali
- order_streamer.py: genera ordini (product, destinazione, urgenza)
- mcp_layer.py: capability MCP (observability + operations + approvals)
- agent_demo.py: agente AI che usa i tool MCP
- dashboard.py: dashboard con coda approvazioni
- data/: file JSONL runtime

## Regole Simulazione

- Magazzino: (0,0)
- Coordinate ordine: lon/lat in [-10000, 10000]
- Batteria: consumo proporzionale ai metri volati
- Una batteria 100% copre andata+ritorno verso il punto piu lontano
- Wear: decadimento randomico verso 0 in base al volo
- Stati drone: landed, takingoff, routing, flying, landing, arrived, returning

## Setup

1. Assicurati di avere Ollama attivo

```bash
ollama serve
ollama pull qwen2.5:7b-instruct
```

2. Variabili ambiente per client OpenAI-compatible

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
```

## Esecuzione rapida

Dalla cartella DroneDemo:

1. Genera telemetria flotta

```bash
python3 drone_streamer.py --data-dir data --ticks 80 --interval 0.3 --seed 7
```

2. Genera ordini

```bash
python3 order_streamer.py --data-dir data --count 25 --interval 0.2 --seed 11
```

3. Esegui agente una volta

```bash
python3 agent_demo.py --data-dir data --model qwen2.5:7b-instruct --max-steps 4
```

4. Avvia dashboard

```bash
python3 dashboard.py --data-dir data --model qwen2.5:7b-instruct --port 8090
```

Apri: http://127.0.0.1:8090

## Avvio con Script Unico

Puoi avviare tutto (drone streamer + order streamer + dashboard + agent loop opzionale) con un solo comando:

```bash
bash start_demo.sh
```

Variabili utili:

```bash
PORT=8095 MODEL=qwen2.5:7b-instruct bash start_demo.sh
```

Disabilitare il loop automatico agente (userai il bottone `Run Agent Now` in dashboard):

```bash
AUTO_AGENT=0 bash start_demo.sh
```

## Policy Human Approval

L agente deve richiedere approvazione umana quando suggerisce:
- add_drone
- abort_order
- checkpoint_drop

In dashboard puoi approvare o rifiutare ogni richiesta dalla coda pending.
