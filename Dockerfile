FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

ENV PORT=8000
EXPOSE ${PORT}

# Use shell form so $PORT env var (set by Railway/other PaaS) gets expanded.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
