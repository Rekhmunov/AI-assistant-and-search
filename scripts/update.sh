#!/usr/bin/env bash
# Safe production update: git pull main, nginx config, rebuild & restart all services.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
BRANCH="${GIT_BRANCH:-main}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi

API_HOST_CHECK="${API_HOST:-api.glosix.ru}"

echo "==> Backup DB (optional)"
bash scripts/backup-db.sh 2>/dev/null || echo "    backup skipped"

if [ -d .git ]; then
  echo "==> Git pull origin ${BRANCH}"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
else
  echo "==> No .git — skip pull"
fi

echo "==> nginx.prod.conf from hosting.config"
bash scripts/render-nginx.sh || true

echo "==> Build & restart containers"
$COMPOSE build
$COMPOSE up -d --remove-orphans

echo "==> Restart internal nginx (pick up nginx.prod.conf)"
$COMPOSE restart nginx

echo "==> Wait for API health"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PROXY_PORT:-18080}/health" -H "Host: ${API_HOST_CHECK}" >/dev/null 2>&1; then
    echo "    OK: http://127.0.0.1:${PROXY_PORT:-18080}/health"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "    FAIL: API not healthy — check: $COMPOSE logs backend --tail 50"
    exit 1
  fi
  sleep 2
done

$COMPOSE ps
echo "==> Update complete"
