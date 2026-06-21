#!/usr/bin/env sh
set -eu
exec python -m uvicorn heatguard.api:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --workers 1
