# ---- Stage 1: build SvelteKit static site ----
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm install @sveltejs/adapter-static
ENV DOCKER=1
RUN npm run build

# ---- Stage 2: serve static files with nginx ----
FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY entrypoint.sh /docker-entrypoint.d/40-inject-api-url.sh
RUN chmod +x /docker-entrypoint.d/40-inject-api-url.sh
ENV PORT=80
ENV API_URL=""
EXPOSE 80
