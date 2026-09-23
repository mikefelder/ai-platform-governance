FROM python:3.14-slim

WORKDIR /app
COPY main.py .

RUN pip install --no-cache-dir \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp

CMD ["python", "main.py"]
