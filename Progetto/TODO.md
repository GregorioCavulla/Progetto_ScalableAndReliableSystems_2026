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
- [x] **Modifiche ai Simulatori**: Implementato sistema di riferimento a [0.0000, 0.0000], aggiunto usura ai droni con soglia di manutenzione, verificata struttura ordini.
- [x] **Architettura Agenti AI**: Implementati Health Agent (Observer/Healer) e Logistic Agent (Dispatcher) con infrastruttura MCP per tool di lettura stato droni, telemetria e scaling K8s.

## 🛠️ Fasi da Implementare

### 1️⃣ Completamento Sistema Decisionale
- [x] Esaminare la stesura finale dei loop in `logistic_ai_brain.py` implementando questi due agenti coordinati.
- [ ] Testare l'intero flusso simulando invio di ordini e usura dei droni.

### 3️⃣ Dashboard Eventi Catastrofici
- [ ] **Dashboard Simulazione Disastri**: Creare uno script o un pannello di controllo per iniettare stress test nel sistema.
  - Generazione di "Esplosioni simultanee" o guasti massivi su larga parte dei droni.
  - Generazione di un picco imprevisto ("Black Friday") in cui gli ordini decuplicano in pochi secondi.
  - Verificare e visualizzare come l'Agente Salute reagisce allo stress infrastrutturale e come il Logistico gestisce l'overflow di coda.

### 4️⃣ Dashboard Osservabilità (Web/HTML)
- [ ] **Pannello Live Logs HTML**: Sviluppare una dashboard web (es. via Flask/FastAPI + WebSocket) per aggregare e mostrare in tempo reale i log generati da tutti i pod, agenti e porte di sistema in un solo punto.