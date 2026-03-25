# Guida all'Avvio del Progetto

L'intero avvio dell'infrastruttura (Broker MQTT, InfluxDB, Server Centrale, Streamers, ecc.) è stato automatizzato tramite uno script bash.

## 1. Prerequisiti

Prima di lanciare lo script, assicuratevi di avere installati e configurati sulla vostra macchina i seguenti strumenti:

- **[Docker](https://docs.docker.com/engine/install/)**: Necessario per il container engine.
- **[Kind (Kubernetes IN Docker)](https://kind.sigs.k8s.io/)**: Utilizzato per creare e gestire il nostro cluster Kubernetes locale.
- **[kubectl](https://kubernetes.io/docs/tasks/tools/)**: Il tool a riga di comando per interagire con il cluster.

## 2. Come avviare il progetto

È sufficiente aprire il terminale, assicurarsi di essere all'interno di questa cartella (`Broker_Streamer_Server`) ed eseguire lo script di avvio:

```bash
bash startup_services.sh
```

*(Lo script potrebbe richiedere la password di root tramite `sudo` per avviare il demone Docker, se non è già in esecuzione)*.

### Cosa fa lo script in automatico?
1. Avvia il demone Docker.
2. Crea un cluster Kubernetes locale tramite **Kind** (configurato tramite il file `cluster.yaml` e chiamato `lab`).
3. Effettua la build di tutte le immagini Docker necessarie per l'infrastruttura (`iot-streamer:v1`, `iot-server:v1`, `iot-toolbox:v1`).
4. Carica le immagini appena create all'interno del nodo Kind.
5. Inizializza i servizi base (Mosquitto per MQTT e InfluxDB) e ne attende l'operatività.
6. Avvia il resto dell'ecosistema (Server Centrale, Streamers e Controller).

## 3. Comandi Utili (Post - Installazione)

Una volta che lo script termina con successo mostrando il messaggio "LABORATORIO OPERATIVO AL 100%", la vostra infrastruttura sarà attiva e funzionante.

Ecco alcuni comandi utili per monitorare o ispezionare il cluster:

- **Visualizzare i log del server centrale in tempo reale:**
  ```bash
  kubectl logs -f deployment/server-centrale
  ```

- **Accedere all'interfaccia di InfluxDB (Database):**
  Per consultare e interrogare il database dal vostro browser, aprite un port-forwarding:
  ```bash
  kubectl port-forward svc/influxdb-service 8086:8086
  ```
  Successivamente aprite il browser all'indirizzo `http://localhost:8086`.
  Username: `admin`
  Password: `password123`

- **Vedere lo stato di tutti i pod (per controllare che tutto giri correttamente):**
  ```bash
  kubectl get pods
  ```
