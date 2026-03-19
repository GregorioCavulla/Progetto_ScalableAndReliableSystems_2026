# Appunti - Architettura Microservizi su Kubernetes (Beta_V2)

## Visione generale
Nel nostro setup ci sono quattro elementi principali che lavorano insieme:
- `Dockerfile`: definisce come costruire l'immagine container di ogni servizio.
- `app.py`: contiene la logica applicativa del microservizio.
- `deployment.yaml`: dice a Kubernetes come eseguire i container (quale immagine usare, quante repliche, probe, env, risorse).
- `service.yaml`: espone i pod in rete interna cluster con un nome stabile e una porta di accesso.

## Ruolo tecnico dei file

### 1) Dockerfile (build-time)
Il Dockerfile descrive il processo di build dell'immagine:
- immagine base (es. Python slim),
- copia codice e dipendenze,
- installazione pacchetti,
- comando di avvio (`CMD`).

Importante: il Dockerfile non viene eseguito da Kubernetes direttamente. Viene usato prima, durante la fase di build (`docker build` o pipeline CI/CD).

### 2) app.py (runtime applicativo)
`app.py` contiene il comportamento del servizio:
- endpoint health (`/health`),
- logica publish/consume verso broker,
- elaborazioni specifiche del microservizio.

In pratica, il container avvia questo processo come entrypoint.

### 3) deployment.yaml (orchestrazione dei pod)
Il Deployment in Kubernetes definisce lo stato desiderato dei pod:
- `image`: quale immagine container avviare,
- `replicas`: quante istanze mantenere attive,
- `env`: variabili d'ambiente per configurare il servizio,
- `livenessProbe` e `readinessProbe`: controllo salute e disponibilita,
- `resources`: richieste/limiti CPU e memoria,
- strategia di rollout (es. RollingUpdate).

Correzione chiave: il Deployment non costruisce immagini. Le immagini devono gia esistere in un registry (o essere importate nel cluster locale).

### 4) service.yaml (networking interno)
Il Service fornisce un endpoint stabile per raggiungere un gruppo di pod tramite label selector:
- seleziona i pod con `selector` (es. `app: custom-broker`),
- espone una porta logica (`port`),
- inoltra verso la porta del container (`targetPort`).

Correzione chiave: il Service non gestisce versioni del software. La versione e legata al tag immagine usato nel Deployment.

## Flusso operativo corretto (end-to-end)
1. Si sviluppa/aggiorna codice in `app.py` e dipendenze.
2. Si definisce la build nel `Dockerfile`.
3. Si costruisce l'immagine (`docker build`) e la si pubblica/importa.
4. Il `deployment.yaml` viene applicato e Kubernetes crea/aggiorna i pod.
5. Il `service.yaml` rende i pod raggiungibili con DNS interno stabile.

## Traduzione veloce in una frase
- Dockerfile = come creare l'immagine.
- app.py = cosa fa il servizio.
- Deployment = come Kubernetes esegue e scala quel servizio.
- Service = come gli altri servizi lo raggiungono in rete.

## Nota pratica per Beta_V2
In questa V2 abbiamo rimosso Redis dalla parte Kubernetes e dalla implementazione minima dei servizi, mantenendo una base semplice e modulare per evoluzioni successive.

## MVP Agentic Controller (implementato)
Abbiamo introdotto una prima logica agentica di dominio nel servizio fleet-agent:
- osserva telemetria droni (`drone.events`) e calcola un indicatore di salute flotta,
- legge il backlog ordini dal broker (`orders.incoming`, `orders.normal`, `orders.urgent`),
- genera raccomandazioni operative su `ops.recommendations`.

Tipi di raccomandazione attivi:
- proposta di aggiungere droni quando il backlog cresce,
- proposta di policy timeout ordini adattiva al carico,
- proposta finestra manutenzione quando la percentuale di droni critici e alta.

Dettagli implementativi:
- broker con endpoint metriche code in `src/custom-broker/app.py` (`/api/queues`),
- controller di dominio in `src/fleet-agent/app.py` con cooldown anti-spam delle raccomandazioni.
