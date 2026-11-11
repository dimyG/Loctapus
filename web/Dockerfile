FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Development stage, selected by deploy/docker-compose.dev.yml: the Vite dev server
# replaces Caddy so a source edit hot-reloads instead of needing a rebuild. It listens
# on 8080 (the port Caddy uses in production) so the URL does not change between modes.
FROM node:24-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 8080
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "8080", "--strictPort"]

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY redirect.conf /etc/caddy/redirect.conf
COPY --from=build /app/dist /srv
