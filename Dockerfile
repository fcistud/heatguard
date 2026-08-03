# HeatGuard — API + React dashboard for Cloud Run (single service, same origin).
# Build:  docker build -t heatguard .
# Run hardened (read-only root + writable cache/tmp tmpfs):
#   docker run --rm -p 8080:8080 --read-only \
#     --tmpfs /tmp:rw,mode=1777 \
#     --tmpfs /var/cache/heatguard:rw,mode=1777,uid=10001,gid=10001 \
#     -e HEATGUARD_CACHE_DIR=/var/cache/heatguard heatguard
#
# Base images are pinned by digest. To refresh pins after security patches, see
# docs/DEPLOY_GCP.md ("Updating base image digests").

# --- Dashboard (Vite) ---------------------------------------------------------
FROM node:24-bookworm-slim@sha256:235600a8101ab264e117b1768e925532262668dc9b581ef1dd7d96ced463b8e7 AS web-build
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci \
    && (npm ls --all --omit=dev --package-lock-only >/tmp/npm-ls.txt 2>&1 || npm ls --all >/tmp/npm-ls.txt 2>&1) \
    && sort -u /tmp/npm-ls.txt > /tmp/npm-deps.txt
COPY web/ ./
# Same origin as API — empty base URL so fetch("/health") works on Cloud Run.
ARG VITE_API_BASE=
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# --- API (Python) -------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEATGUARD_DATA_DIR=/app/data \
    HEATGUARD_CACHE_DIR=/var/cache/heatguard \
    HEATGUARD_STATIC_DIR=/app/static \
    HEATGUARD_LANDING_DIR=/app/landing \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Frozen hash-verified install from committed requirements.txt (api + ml).
# No build-time lock re-resolution; regenerate via scripts/export_requirements.py.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

COPY data ./data
COPY landing ./landing
COPY --from=web-build /build/web/dist ./static
COPY --from=web-build /tmp/npm-deps.txt /app/.build-meta/npm-deps.txt

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && groupadd --gid 10001 heatguard \
    && useradd --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin heatguard \
    && mkdir -p /var/cache/heatguard /app/.build-meta \
    && chown -R 10001:10001 /app /var/cache/heatguard

USER 10001:10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
