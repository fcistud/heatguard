#!/usr/bin/env sh
set -eu
python -c 'import sys; print(f"heatguard.runtime python={sys.version.split()[0]}", flush=True)'
exec python -m uvicorn heatguard.api:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --workers 1
