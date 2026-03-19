# Scalable and Reliable Systems - Drone Logistics

Questo repository implementa un sistema logistico di droni con architettura event-driven. I microservizi sono disaccoppiati tramite Custom Broker e orchestrati su Kubernetes (k3d), con logica AI simulata per vendite e gestione flotta.

## Architettura dei Microservizi
- **order-streamer**: genera ordini in XML e li invia alla coda `orders`.
- **sales-agent**: consuma gli ordini, calcola priorita e distanza, e li inserisce nel database (Redis).
- **drone-fleet**: emette telemetria JSON (GPS, batteria, usura) su `drone.events` con repliche multiple.
- **fleet-agent**: rileva anomalie sui log dei droni e produce alert.
- **custom-broker**: broker AMQP per la coda eventi.
- **redis**: database fittizio per lo storage degli ordini.

## Teoria: Perche Event-Driven e Affidabile
L'architettura event-driven introduce un livello di disaccoppiamento tra generatori e consumatori. Il broker Custom Broker funge da buffer durevole: i messaggi restano in coda anche quando i servizi a valle sono occupati o temporaneamente non disponibili. Questo abilita:

- **Scalabilita orizzontale**: i consumer possono essere scalati indipendentemente e ogni replica consuma dalla stessa coda.
- **Assorbimento dei picchi**: i burst di ordini o telemetria vengono accodati e processati in modo asincrono.
- **Affidabilita**: con `durable` e `ack`, i messaggi non vanno persi e possono essere riprocessati.

In termini di sistemi, la coda introduce una forma di backpressure controllata, riducendo la probabilita di overload e garantendo un throughput stabile.

## Esecuzione Locale
Prerequisiti: Docker, kubectl, k3d.

1. Crea il cluster k3d tramite il file IaC:
   ```bash
   k3d cluster create --config cluster-config.yaml
   ```
2. Avvia l'intero stack (build immagini, import su k3d, deploy):
   ```bash
   ./setup.sh
   ```

Lo script esegue le build delle immagini locali, le importa nel cluster con `k3d image import` e applica i manifesti in `k8s/`.

## Monitoraggio

### Custom Broker Dashboard
Esporre la dashboard di Custom Broker in locale:
```bash
kubectl port-forward svc/custom-broker 15672:15672
```
Accedi a `http://localhost:15672` e usa le credenziali:
- user: `srs`
- pass: `srs123`

### Log Fleet AI
Stream dei log in tempo reale per i rilevamenti di anomalie:
```bash
kubectl logs -l app=fleet-agent -f
```

## Struttura Repository
- [k8s/deployment.yaml](k8s/deployment.yaml) contiene tutti i Deployment (microservizi, Custom Broker, Redis) con liveness/readiness.
- [k8s/service.yaml](k8s/service.yaml) contiene i Service ClusterIP per i componenti.
- `src/` contiene il codice Python e i Dockerfile dei microservizi.
