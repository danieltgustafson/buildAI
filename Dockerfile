FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

ENV PORT=8000
EXPOSE 8000

# Use python -m to read PORT from env at runtime (works even without shell expansion)
CMD ["python", "-m", "app.main"]
