FROM node:20-slim

# Pre-compiled Kraken CLI binary (copied from repo root via build context)
COPY kraken /usr/local/bin/kraken
RUN chmod +x /usr/local/bin/kraken

WORKDIR /app

COPY erc8004/package.json erc8004/package-lock.json* ./
RUN npm ci || npm install

COPY erc8004/ .

CMD ["npx", "ts-node", "scripts/run-agent.ts"]
