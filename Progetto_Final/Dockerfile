FROM python:3.10-slim

# Impostiamo l'ambiente come non interattivo per apt-get e forziamo la lingua
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

WORKDIR /app

# Copia e installa unicamente le dipendenze essenziali
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia gli script del progetto
COPY . /app/

# Il comando di default verrà sovrascritto nei manifesti di Kubernetes
CMD ["python", "-u", "central_server.py"]