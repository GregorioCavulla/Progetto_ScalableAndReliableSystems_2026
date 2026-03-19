FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_observability.py mcp_remediation.py README.md ./

CMD ["python", "mcp_observability.py"]
