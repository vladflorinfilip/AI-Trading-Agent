# ---- Stage 1: build Kraken CLI for Linux ----
FROM rust:1.88-slim AS kraken-build
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
RUN cargo install --git https://github.com/krakenfx/kraken-cli.git --locked

# ---- Stage 2: Node.js agent loop ----
FROM node:20-slim

COPY --from=kraken-build /usr/local/cargo/bin/kraken /usr/local/bin/kraken

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

CMD ["npx", "ts-node", "scripts/run-agent.ts"]
