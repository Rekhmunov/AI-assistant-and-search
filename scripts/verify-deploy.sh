#!/usr/bin/env bash
# Quick checks after update on VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi

APP_HOST="${APP_HOST:-glosix.ru}"
API_HOST="${API_HOST:-api.glosix.ru}"

echo "==> Docker containers"
$COMPOSE ps

echo ""
echo "==> Alembic revision (inside backend)"
$COMPOSE exec -T backend alembic current || true

echo ""
echo "==> Backend direct (inside container)"
$COMPOSE exec -T backend curl -sf http://127.0.0.1:8000/health 2>/dev/null | head -c 300 || echo "FAIL (backend not listening)"
echo ""

echo ""
echo "==> API health (docker nginx, Host: ${APP_HOST})"
curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${APP_HOST}" | head -c 500 || echo "FAIL"
echo ""

echo "==> API health (docker nginx, Host: ${API_HOST})"
curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${API_HOST}" | head -c 500 || echo "FAIL"
echo ""

echo ""
echo "==> Public app /api/health"
curl -sf "https://${APP_HOST}/api/health" | head -c 500 || echo "FAIL"
echo ""

echo ""
echo "==> Public API root (expect 404)"
curl -sI "https://${API_HOST}/" | head -3 || echo "FAIL"
echo ""
echo "==> Public API /health"
curl -sf "https://${API_HOST}/health" | head -c 500 || echo "FAIL (/health)"
echo ""

echo ""
echo "==> Backend logs (last 30 lines)"
$COMPOSE logs backend --tail 30
