# ---- Stage 1: build Kraken CLI from source ----
FROM rust:1.88-slim AS kraken-build
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
RUN cargo install --git https://github.com/krakenfx/kraken-cli.git --locked

# ---- Stage 2: Python backend ----
FROM python:3.12-slim

COPY --from=kraken-build /usr/local/cargo/bin/kraken /usr/local/bin/kraken

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY config.yaml .

ENV PORT=8000
EXPOSE ${PORT}

CMD uvicorn backend.api:app --host 0.0.0.0 --port ${PORT}
