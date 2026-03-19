FROM python:3.10-slim

WORKDIR /app
COPY app.py /app/app.py
RUN pip install --no-cache-dir requests redis

CMD ["python", "app.py"]
