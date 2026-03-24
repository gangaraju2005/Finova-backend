# ── Stage 1: Build dependencies ──────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libjpeg62-turbo-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

EXPOSE 8000

CMD ["gunicorn", "core.wsgi:application", "--config", "gunicorn.conf.py"]
