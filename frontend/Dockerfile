# Frontend image: React build served by nginx.
# Build from the REPO ROOT, to match the backend:
#     docker build -t portfolio-construction-web:latest -f frontend/Dockerfile .
#
# nginx serves the static files and proxies /api to the backend, so the browser talks to a
# single origin: no CORS setup, and no backend URL baked in at build time. Point it at a
# different backend with the API_UPSTREAM variable at run time.

FROM node:20-alpine AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

ENV API_UPSTREAM=http://api:8000 \
    TZ=Asia/Ho_Chi_Minh

COPY --from=build /app/dist /usr/share/nginx/html
# The official image runs envsubst over /etc/nginx/templates at startup.
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
