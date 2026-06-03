#!/usr/bin/env bash
# Дозавершить update, если скрипт завис на ожидании backend (Ctrl+C на update.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"
APP_HOST="${APP_HOST:-glosix.ru}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi

echo "==> Статус контейнеров"
$COMPOSE ps

echo ""
echo "==> Логи backend (последние 40 строк)"
$COMPOSE logs backend --tail 40

echo ""
echo "==> Миграции"
$COMPOSE exec -T backend alembic upgrade head

echo ""
echo "==> Frontend + nginx"
$COMPOSE up -d --force-recreate frontend admin nginx

echo ""
echo "==> Health"
for i in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${APP_HOST}" >/dev/null 2>&1; then
    echo "    API OK"
    exit 0
  fi
  sleep 2
done

echo "    API FAIL — см. docker compose logs backend nginx"
exit 1
