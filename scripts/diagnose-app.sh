#!/usr/bin/env bash
# Сбор диагностики при пустом экране app.glosix.ru
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"
APP_HOST="${APP_HOST:-app.glosix.ru}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
  PROXY_PORT="${PROXY_PORT:-18080}"
  APP_HOST="${APP_HOST:-$APP_HOST}"
fi

echo "========== Glosix diagnose $(date -Iseconds) =========="
echo "PWD: $ROOT"
echo "GIT: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo ""

echo "==> Docker ps"
$COMPOSE ps || true
echo ""

echo "==> Alembic"
$COMPOSE exec -T backend alembic current 2>&1 || true
echo ""

echo "==> API /api/health"
curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${APP_HOST}" 2>&1 || echo "FAIL"
echo ""
echo ""

echo "==> App index.html (first 30 lines)"
curl -sf "http://127.0.0.1:${PROXY_PORT}/" -H "Host: ${APP_HOST}" 2>&1 | head -30 || echo "FAIL"
echo ""

JS_PATH=$(curl -sf "http://127.0.0.1:${PROXY_PORT}/" -H "Host: ${APP_HOST}" 2>/dev/null | grep -oE '/assets/index-[^"[:space:]]+\.js' | head -1 || true)
echo "==> App JS bundle: ${JS_PATH:-NOT FOUND}"
if [ -n "$JS_PATH" ]; then
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PROXY_PORT}${JS_PATH}" -H "Host: ${APP_HOST}" || echo "000")
  echo "    HTTP $CODE"
  if [ "$CODE" = "200" ]; then
    curl -sf "http://127.0.0.1:${PROXY_PORT}${JS_PATH}" -H "Host: ${APP_HOST}" | head -c 120 | tr '\n' ' '
    echo "..."
  fi
fi
echo ""
echo ""

echo "==> Backend logs (last 40)"
$COMPOSE logs backend --tail 40 2>&1 || true
echo ""

echo "==> Nginx logs (last 20)"
$COMPOSE logs nginx --tail 20 2>&1 || true
echo ""

echo "==> Frontend container logs (last 15)"
$COMPOSE logs frontend --tail 15 2>&1 || true
echo ""
echo "========== end =========="
