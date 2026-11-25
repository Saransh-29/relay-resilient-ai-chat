# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Optional build-time fallback. The runtime /config.js (from API_BASE_URL) takes precedence.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ---- Runtime stage ----
FROM nginx:1.27-alpine AS runtime
ENV API_BASE_URL=http://localhost:8000
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/40-relay-config.sh /docker-entrypoint.d/40-relay-config.sh
RUN chmod +x /docker-entrypoint.d/40-relay-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
