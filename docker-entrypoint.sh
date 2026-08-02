#!/usr/bin/env sh
set -eu

# Seed the runtime cache from the baked offline baseline when CACHE_DIR is
# redirected (read-only root + tmpfs). Local defaults share DATA_DIR/cache.
DATA_DIR="${HEATGUARD_DATA_DIR:-/app/data}"
CACHE_DIR="${HEATGUARD_CACHE_DIR:-${DATA_DIR}/cache}"
BASELINE="${DATA_DIR}/cache"
NUMBA_CACHE_DIR="${NUMBA_CACHE_DIR:-/tmp/numba_cache}"

# pythermalcomfort/numba needs a writable cache locator under read-only root.
mkdir -p "${NUMBA_CACHE_DIR}"

if [ -d "${BASELINE}" ] && [ "${CACHE_DIR}" != "${BASELINE}" ]; then
  mkdir -p "${CACHE_DIR}"
  # Copy only when the mount looks empty so we don't clobber warm writes.
  if [ -z "$(ls -A "${CACHE_DIR}" 2>/dev/null || true)" ]; then
    cp -a "${BASELINE}/." "${CACHE_DIR}/"
  fi
fi

python -c 'import os, sys; print(f"heatguard.runtime python={sys.version.split()[0]} uid={os.getuid()}", flush=True)'
exec python -m uvicorn heatguard.api:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --workers 1
