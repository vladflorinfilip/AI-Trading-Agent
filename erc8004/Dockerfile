FROM node:20-slim

COPY kraken /usr/local/bin/kraken
RUN chmod +x /usr/local/bin/kraken

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

CMD ["npx", "ts-node", "scripts/run-agent.ts"]
