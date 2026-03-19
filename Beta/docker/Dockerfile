# Multi-stage build per ottimizzare le dimensioni dell'immagine finale
# Fase 1: Build
FROM node:18-alpine AS builder

# Imposta la directory di lavoro all'interno del container
WORKDIR /usr/src/app

# Copia i file delle dipendenze per sfruttare la cache dei layer di Docker
COPY ../src/package*.json ./

# Installa solo le dipendenze di produzione (scarta devDependencies)
RUN npm install --omit=dev

# Copia il resto del codice sorgente
COPY ../src/ .

# Fase 2: Produzione
FROM node:18-alpine

# Aggiunge un utente non root per motivi di sicurezza (Security constraints K8s)
USER node

WORKDIR /usr/src/app

# Copia gli artefatti dalla fase di build
COPY --from=builder --chown=node:node /usr/src/app ./

# Esponi la porta
EXPOSE 3000

# Avvia l'applicazione
CMD ["npm", "start"]
