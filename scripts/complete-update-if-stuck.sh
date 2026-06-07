#!/usr/bin/env bash
# Дозавершить update после сбоя или Ctrl+C. Обязательно пересобирает backend/worker.
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

# shellcheck source=scripts/update-prod.sh
_wait_backend_health() {
  local label="$1"
  local max_attempts="${2:-45}"
  echo "    ${label}: ждём backend /health (до $((max_attempts * 2)) с)…"
  for i in $(seq 1 "$max_attempts"); do
    if $COMPOSE exec -T backend curl -sf --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
      echo "    ${label}: backend /health OK (~$((i * 2)) с)"
      return 0
    fi
    if [ $((i % 5)) -eq 0 ]; then
      local st
      st="$($COMPOSE ps backend --format '{{.Status}}' 2>/dev/null | head -1 || echo unknown)"
      echo "    … попытка ${i}/${max_attempts}, статус: ${st}"
    fi
    if [ "$i" -eq "$max_attempts" ]; then
      echo "    ${label}: backend /health FAIL"
      $COMPOSE logs backend --tail 40
      return 1
    fi
    sleep 2
  done
}

echo "==> Git: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "==> Пересборка backend + worker (код с диска → образ)"
$COMPOSE build backend worker

echo "==> Запуск backend + worker"
$COMPOSE up -d --force-recreate backend worker

if ! _wait_backend_health "backend" 45; then
  echo "ERROR: backend не поднялся. Проверьте: docker compose -f docker-compose.prod.yml logs backend --tail 50"
  exit 1
fi

echo "==> Миграции"
$COMPOSE exec -T backend alembic upgrade head

echo "==> Frontend + admin + nginx"
$COMPOSE build --no-cache frontend
$COMPOSE build admin
$COMPOSE up -d --force-recreate frontend admin nginx

echo "==> Health (127.0.0.1:${PROXY_PORT})"
for i in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${APP_HOST}" >/dev/null 2>&1; then
    echo "    API OK"
    $COMPOSE ps
    exit 0
  fi
  sleep 2
done

echo "    API FAIL"
$COMPOSE logs nginx --tail 15
exit 1
