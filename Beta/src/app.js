/**
 * srs-demo-app
 * Entrypoint dell'applicazione Node.js.
 * Utilizzato per validare il bilanciamento del carico testando il pod su cui è in esecuzione l'istanza.
 */
const express = require('express');
const os = require('os');

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => {
    // Restituisce il nome dell'host (che in Kubernetes corrisponde al nome del Pod)
    const podName = os.hostname();
    res.json({
        message: "Hello World from Scalable and Reliable Systems!",
        pod: podName,
        status: "OK",
        timestamp: new Date().toISOString()
    });
});

app.get('/health', (req, res) => {
    res.status(200).send("Healthy");
});

app.listen(PORT, () => {
    console.log(`Server is listening on port ${PORT}`);
});
