FROM python:3.9-slim
RUN pip install paho-mqtt influxdb-client
# Cambiamo questa riga per copiare tutto
COPY . /app/
WORKDIR /app
# Il CMD rimane questo, ma lo sovrascriviamo nel file yaml per il server
CMD ["python", "streamer.py"]
