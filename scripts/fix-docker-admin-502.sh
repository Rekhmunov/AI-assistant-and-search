#!/usr/bin/env bash
# Быстрое восстановление admin.glosix.ru после 502 (Docker nginx → admin:80).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"
ADMIN_HOST="${ADMIN_HOST:-admin.glosix.ru}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi
PROXY_PORT="${PROXY_PORT:-18080}"
ADMIN_HOST="${ADMIN_HOST:-admin.glosix.ru}"

if ! grep -q "resolver 127.0.0.11" nginx/nginx.prod.conf 2>/dev/null; then
  echo "WARN: в nginx/nginx.prod.conf нет resolver 127.0.0.11 — после пересборки возможен 502"
  if [ -f hosting.config ]; then
    echo "==> render nginx from hosting.config"
    bash scripts/render-nginx.sh
  fi
fi

echo "==> Пересоздаём admin и nginx"
$COMPOSE up -d --force-recreate admin nginx

echo "==> Статус"
$COMPOSE ps admin nginx

for i in $(seq 1 15); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PROXY_PORT}/login" -H "Host: ${ADMIN_HOST}" || echo "000")
  if [ "$CODE" = "200" ]; then
    echo "==> admin OK (HTTP 200 на /login)"
    exit 0
  fi
  sleep 2
done

echo "ERROR: admin всё ещё HTTP ${CODE:-000}"
$COMPOSE logs admin --tail 40
$COMPOSE logs nginx --tail 40
exit 1
