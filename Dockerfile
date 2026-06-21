# HeatGuard — API + React dashboard for Cloud Run (single service, same origin).
# Build:  docker build -t heatguard .
# Run with demo pre-warm (first page load fast; container start ~30–90s longer):
#   docker run --rm -p 8080:8080 -e HEATGUARD_WARM_DEMOS=1 heatguard

# --- Dashboard (Vite) ---------------------------------------------------------
FROM node:22-bookworm-slim AS web-build
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Same origin as API — empty base URL so fetch("/health") works on Cloud Run.
ARG VITE_API_BASE=
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# --- API (Python) -------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEATGUARD_DATA_DIR=/app/data \
    HEATGUARD_STATIC_DIR=/app/static \
    HEATGUARD_LANDING_DIR=/app/landing \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[api,ml]"

COPY data ./data
COPY landing ./landing
COPY --from=web-build /build/web/dist ./static

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
