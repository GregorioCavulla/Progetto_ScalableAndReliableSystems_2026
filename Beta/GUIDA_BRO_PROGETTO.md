# Guida Bro al Progetto (Versione Semplice ma Completa)

## 1) In due righe: che progetto e
Immagina una azienda che consegna pezzi con droni.
Questo progetto simula proprio quello: arrivano ordini, i droni lavorano, il sistema controlla se ci sono problemi, e un "assistente intelligente" aiuta a capire cosa fare quando qualcosa va storto.

Obiettivo finale: non fare solo una demo carina, ma un sistema che regga anche quando c e caos (carico alto, errori, servizi giu).

---

## 2) Prima base: cos e Kubernetes (spiegato easy)
Kubernetes e un "capo cantiere" dei container.
Tu hai tanti piccoli programmi (servizi), Kubernetes li avvia, li tiene in piedi e li rimpiazza se cadono.

Pensa cosi:
- Container = una scatola con dentro un servizio pronto a girare.
- Pod = il posto dove gira quel container.
- Deployment = la regola che dice quanti pod voglio e come aggiornarli.
- Service = il "nome stabile" per parlare con un servizio (anche se i pod cambiano).

Perche ci serve:
- Se un servizio muore, riparte da solo.
- Se serve piu forza, aumenti repliche.
- Tutto e piu ordinato e ripetibile.

Nel nostro progetto usiamo k3d, cioe un Kubernetes locale dentro Docker, perfetto per sviluppare sul pc.

---

## 3) Come funziona il nostro progetto, in modo pratico

### L idea generale
Il sistema e fatto a microservizi, cioe tanti pezzi piccoli che collaborano.
Non si parlano tutti direttamente: usano un "broker" centrale dove si scambiano messaggi.

### Flusso principale
1. Un servizio genera ordini.
2. Un altro servizio prende gli ordini e decide priorita.
3. I droni simulati mandano telemetria (batteria, posizione, stato).
4. Un agente controlla la telemetria e segnala anomalie.
5. Una dashboard mostra cosa sta succedendo live.

### Chi fa cosa
- order-streamer: crea ordini finti.
- sales-agent: legge ordini e li classifica.
- drone-fleet: simula tanti droni che inviano aggiornamenti.
- fleet-agent: controlla se un drone e in difficolta.
- custom-broker: il centro messaggi + dashboard.
- redis: memoria veloce per dati utili (es ordini prioritari).

---

## 4) Parte "assistente intelligente" (MCP) in parole umane
Abbiamo 2 ruoli separati:

1. Observability Agent
- Guarda lo stato del sistema.
- Legge metriche, pod, log.
- Non dovrebbe fare azioni distruttive.

2. Remediation Agent
- Fa azioni operative (es scalare repliche, restart controllato).
- Ha paletti di sicurezza (es limite repliche, approvazione umana per azioni rischiose).

Perche e importante separarli:
- Chi osserva non deve avere troppi poteri.
- Chi puo agire deve essere controllato.

---

## 5) Perche questo progetto esiste (senso vero)
Il prof non vuole solo "funziona sul mio pc".
Vuole vedere che sai costruire un sistema che:
- regge sotto stress,
- non crolla al primo guasto,
- e controllabile,
- non fa azioni pericolose a caso,
- ha senso anche nei costi.

Quindi non basta codice: servono anche scelte ragionate e prove reali.

---

## 6) Come partire a implementare da zero (roadmap bro)

## Step 1 - Fai girare il progetto in locale
1. Installa Docker, kubectl, k3d.
2. Entra nella cartella Beta.
3. Crea il cluster k3d.
4. Lancia lo script setup per build + deploy.
5. Controlla che i pod siano in stato buono.

Se tutto ok, hai la base viva su cui lavorare.

## Step 2 - Capisci il flusso messaggi
1. Guarda quali code/topic usa ogni servizio.
2. Controlla che i nomi siano coerenti tra chi pubblica e chi consuma.
3. Prova con log live per vedere se gli eventi passano davvero.

Se qui c e mismatch, prima sistema questo: e il cuore del progetto.

## Step 3 - Rendi il sistema robusto
1. Gestione errori: timeout, retry, backoff.
2. Evita doppie elaborazioni (idempotenza base).
3. Definisci comportamento quando un pezzo va giu (degradazione controllata).

## Step 4 - Migliora visibilita
1. Log chiari e consistenti in tutti i servizi.
2. Dashboard che faccia vedere code, droni, alert, lock sicurezza.
3. Traccia azioni importanti in un audit log persistente.

## Step 5 - Sistema la parte agentica in sicurezza
1. Ruolo osservazione separato dal ruolo azione.
2. Azioni rischiose sempre con approvazione umana.
3. Limite costi e limite passi per evitare loop infiniti.
4. Se c e dubbio: escalation, non azione azzardata.

## Step 6 - Fai i test di crisi (quelli che piacciono al prof)
Devi provare almeno:
- servizio crashato,
- redis non disponibile,
- broker non disponibile,
- richieste malformate,
- congestione coda,
- rete lenta / timeout.

Per ogni test scrivi:
- cosa hai rotto,
- cosa ti aspettavi,
- cosa e successo,
- come hai recuperato,
- in quanto tempo.

## Step 7 - Chiudi con report serio
Nel report finale metti:
- architettura scelta,
- perche e affidabile/scalabile,
- come osservi il sistema,
- cosa puo fare l agente e cosa no,
- policy di sicurezza,
- test di failure,
- costi, SLO, ROI/ROA.

---

## 7) Errori classici da evitare
- Dire che il sistema e affidabile senza prove.
- Usare nomi code incoerenti tra servizi.
- Fare una dashboard bella ma inutile per diagnosi.
- Dare troppi poteri all agente senza guardrail.
- Dimenticare parte economica (costi, trade-off, ROI).

---

## 8) Mini glossario super rapido
- Scalabile: regge piu lavoro aumentando risorse.
- Affidabile: continua a funzionare anche con guasti.
- Osservabilita: capisci cosa sta succedendo dentro il sistema.
- Guardrail: regole di sicurezza che impediscono azioni pericolose.
- Human in the loop: un umano deve approvare azioni ad alto rischio.
- SLO: obiettivi misurabili di qualita del servizio.

---

## 9) Versione ultra corta da dire a voce
"Abbiamo costruito una piattaforma droni a microservizi su Kubernetes. I servizi comunicano con eventi, c e monitoraggio live, e c e un layer agentico MCP diviso tra osservazione e azione controllata. Il focus non e solo farla funzionare, ma dimostrare che resta stabile e sicura anche sotto guasti, rispettando limiti operativi e di costo."

---

## 10) Prossimo passo consigliato (subito pratico)
Apri il piano principale e lavora in questo ordine:
1. coerenza flusso eventi,
2. robustezza errore/retry,
3. guardrail agent,
4. test di failure,
5. report economico/tecnico finale.

Se fai bene questi 5 blocchi, arrivi davvero vicino alla conformita piena.
