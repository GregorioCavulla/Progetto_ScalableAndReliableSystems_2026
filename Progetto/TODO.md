# 🎯 TODO: Sviluppo Progetto Droni (Versione Beta)

Questo documento traccia i passaggi e l'avanzamento per la versione Beta del sistema di gestione flotta droni. Al centro del sistema, l'intelligenza nativa vanilla sostituisce CrewAI.

## ✅ Fasi Completate
- [x] **Digital Twin dei Droni**: Creato `drone_simulator.py` con macchina a stati (`IDLE`, `IN_DELIVERY`, `RETURNING`, `MAINTENANCE`), consumo batteria e volo vettoriale.
- [x] **Simulatore Clienti**: Creato `client_simulator.py` per inviare pacchetti JSON su MQTT contenenti ID ordine, coordinate e priorità.
- [x] **Server Centrale e Database**: Creato `central_server.py` che ascolta broker MQTT e persiste telemetria flotta e coda ordini in **InfluxDB** usando il client Python ufficiale.
- [x] **Infrastruttura Kubernetes (Kind)**: Creati manifesti YAML per Droni, Client, Server, InfluxDB e Mosquitto.
- [x] **Script di Avvio e Spegnimento**: Sviluppati `start_cluster.py` e `stop_cluster.py` per gestire l'intero ciclo di vita automatizzato dell'ambiente.
- [x] **DevContainer**: Configurato ambiente VS Code per sharing del progetto (Docker-in-Docker, Python 3.10, Kind e configurazioni LLM integrate).
- [x] **Struttura base LLM**: Abbozzato `logistic_ai_brain.py` come orchestratore AI Python vanilla (con proxy LiteLLM e chiavi iniettate da env).

## 🛠️ Fasi da Implementare

### 1️⃣ Modifiche ai Simulatori
- [ ] **Sistema di riferimento**: Reimpostare le coordinate della Base al punto [0.0000, 0.0000] sia in `drone_simulator.py` che in `client_simulator.py`.
- [ ] **Drone Usura (Wear)**: Aggiungere in `drone_simulator.py` un livello di usura (`wear`) incrementale e casuale durante il volo. Se supera una soglia, lo stato del drone potrebbe cambiare.
- [ ] **Coordinate di consegna**: Verificare/Aggiornare la struttura ordini in `client_simulator.py` per confermare le coordinate corrette di consegna ed eventuali dinamiche legate al nuovo sistema di riferimento 0.000.

### 2️⃣ Architettura Agenti AI
*(Al posto del generico loop ReAct precedente, divideremo i task su due agenti)*

- [ ] **Agente Salute Droni (Observer/Healer)**
  - Legge le telemetrie da InfluxDB o state-memory.
  - Verifica i droni andati in KO (es: `batteria == 0` o `wear` eccessivo in `MAINTENANCE`).
  - *Rimediazione (Infrastrutturale)*: Su richiesta esplicita del design, questo agente scalerà il numero di droni interagendo con le API K8s (Kubectl command o client Kubernetes) in caso di flotta troppo danneggiata.

- [ ] **Agente Ordini Droni (Logistico/Dispatcher)**
  - Legge telemetrie e coda ordini.
  - Riceve il contesto spaziale (es: Drone X a coordinate [0.1, 0.5]) e l'ordine da spedire.
  - Sceglie il drone più idoneo in stato `IDLE`.
  - Invia payload MQTT al drone target per l'assegnazione ("consegna l'ordine Z").

### 3️⃣ Completamento Sistema Decisionale
- [ ] Esaminare la stesura finale dei loop in `logistic_ai_brain.py` implementando questi due agenti coordinati.
- [ ] Testare l'intero flusso simulando invio di ordini e usura dei droni.

### 4️⃣ Dashboard Eventi Catastrofici
- [ ] **Dashboard Simulazione Disastri**: Creare uno script o un pannello di controllo per iniettare stress test nel sistema.
  - Generazione di "Esplosioni simultanee" o guasti massivi su larga parte dei droni.
  - Generazione di un picco imprevisto ("Black Friday") in cui gli ordini decuplicano in pochi secondi.
  - Verificare e visualizzare come l'Agente Salute reagisce allo stress infrastrutturale e come il Logistico gestisce l'overflow di coda.

### 5️⃣ Dashboard Osservabilità (Web/HTML)
- [ ] **Pannello Live Logs HTML**: Sviluppare una dashboard web (es. via Flask/FastAPI + WebSocket) per aggregare e mostrare in tempo reale i log generati da tutti i pod, agenti e porte di sistema in un solo punto.