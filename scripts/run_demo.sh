#!/usr/bin/env bash
# One-command HeatGuard demo: API + React dashboard.
#   scripts/run_demo.sh           # start both servers (deps already installed)
#   scripts/run_demo.sh --setup   # install Python + web deps first, then start
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

if [[ "${1:-}" == "--setup" ]]; then
  echo "==> Installing Python package + deps"
  pip install -e . -q && pip install -r requirements.txt -q
  echo "==> Installing web deps"
  ( cd web && npm install )
fi

echo "==> Caching demo weather (Open-Meteo; skips if already cached)"
heatguard fetch-demo

echo "==> Starting API on http://localhost:${API_PORT}"
python3 -m uvicorn heatguard.api:app --port "${API_PORT}" > /tmp/heatguard_api.log 2>&1 &
API_PID=$!
trap 'kill ${API_PID} 2>/dev/null || true' EXIT

# wait for the API to answer
for _ in $(seq 1 30); do
  curl -s "http://localhost:${API_PORT}/health" >/dev/null 2>&1 && break
  sleep 1
done
echo "    API health: $(curl -s "http://localhost:${API_PORT}/health" || echo 'not up — see /tmp/heatguard_api.log')"

echo "==> Starting dashboard on http://localhost:${WEB_PORT}  (Ctrl-C to stop both)"
echo "    (CLI alternative:  heatguard demo dubai   |   heatguard roi riyadh)"
cd web
VITE_API_BASE="http://localhost:${API_PORT}" npm run dev -- --port "${WEB_PORT}"
