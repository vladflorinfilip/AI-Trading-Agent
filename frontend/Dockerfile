# ---- Stage 1: build SvelteKit static site ----
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm install @sveltejs/adapter-static
ENV DOCKER=1
RUN npm run build

# ---- Stage 2: serve with nginx + reverse proxy to backend ----
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
