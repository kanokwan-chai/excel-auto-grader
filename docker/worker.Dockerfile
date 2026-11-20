FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-calc \
    libreoffice-core \
    fonts-thai-tlwg \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY excel_engine /app/excel_engine
COPY backend /app/backend
COPY workers /app/workers

RUN useradd -m workeruser && mkdir -p /app/storage_data && chown -R workeruser:workeruser /app
USER workeruser

CMD ["celery", "-A", "workers.celery_app:celery_app", "worker", "--loglevel=info", "--concurrency=2"]
