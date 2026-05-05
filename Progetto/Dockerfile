FROM python:3.10-slim

WORKDIR /app

# Installa unicamente le dipendenze essenziali
RUN pip install --no-cache-dir paho-mqtt influxdb-client

# Copia gli script del progetto
COPY . /app/

# Il comando di default verrà sovrascritto nei manifesti di Kubernetes
CMD ["python", "central_server.py"]