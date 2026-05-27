#!/usr/bin/env bash
# Безопасное обновление production (без затирания .env).
# Вызывайте после: git pull origin main
#   bash scripts/update-prod.sh
#
# Не трогает: .env, hosting.config
# nginx.prod.conf пересобирается ТОЛЬКО если файл пустой/placeholder/без ADMIN_HOST
# После build frontend/admin — всегда force-recreate nginx (иначе 502 на /thread)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"
API_HOST_CHECK="${API_HOST:-api.glosix.ru}"
APP_HOST_CHECK="${APP_HOST:-app.glosix.ru}"
ADMIN_HOST_CHECK="${ADMIN_HOST:-admin.glosix.ru}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
  PROXY_PORT="${PROXY_PORT:-18080}"
  API_HOST_CHECK="${API_HOST:-$API_HOST_CHECK}"
  APP_HOST_CHECK="${APP_HOST:-$APP_HOST_CHECK}"
  ADMIN_HOST_CHECK="${ADMIN_HOST:-$ADMIN_HOST_CHECK}"
fi

echo "==> Glosix update-prod (main) @ $(pwd)"

if [ ! -f .env ]; then
  echo "ERROR: нет .env — создайте вручную (cp .env.production.example .env && nano .env)"
  exit 1
fi

if grep -q '^POSTGRES_PASSWORD=$' .env 2>/dev/null || grep -q 'CHANGE_ME' .env 2>/dev/null; then
  echo "WARN: в .env есть пустые секреты или CHANGE_ME — проверьте перед продом"
fi

_nginx_needs_render() {
  [ ! -f nginx/nginx.prod.conf ] && return 0
  grep -q "make configure" nginx/nginx.prod.conf 2>/dev/null && return 0
  grep -q 'server_name ${' nginx/nginx.prod.conf 2>/dev/null && return 0
  if ! grep -qF "server_name ${ADMIN_HOST_CHECK};" nginx/nginx.prod.conf 2>/dev/null; then
    return 0
  fi
  if ! grep -q "resolver 127.0.0.11" nginx/nginx.prod.conf 2>/dev/null; then
    return 0
  fi
  return 1
}

if _nginx_needs_render; then
  if [ -f hosting.config ]; then
    echo "==> nginx.prod.conf: render from hosting.config"
    bash scripts/render-nginx.sh
  else
    echo "WARN: nginx.prod.conf неполный, hosting.config нет — не перезаписываем (правьте вручную)"
  fi
else
  echo "==> nginx.prod.conf: OK (не перезаписываем)"
fi

export GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "==> GIT_COMMIT=${GIT_COMMIT}"

echo "==> Backup DB (optional)"
bash scripts/backup-db.sh 2>/dev/null || echo "    backup skipped"

echo "==> Build: backend, frontend, admin, worker"
$COMPOSE build --pull backend frontend admin worker

echo "==> Start stack"
$COMPOSE up -d --remove-orphans

if grep -qE '^(ANTHROPIC_API_KEY|DEEPSEEK_API_KEY)=.+' .env 2>/dev/null; then
  echo "==> ANTHROPIC/DEEPSEEK API key в .env — пересоздаём backend/worker (подхват ключа)"
  $COMPOSE up -d --force-recreate backend worker
fi

echo "==> Recreate frontend + nginx (новый JS и upstream IP)"
$COMPOSE up -d --force-recreate frontend nginx

echo "==> Alembic migrations"
$COMPOSE exec -T backend alembic upgrade head

if grep -qE '^DEEPSEEK_API_KEY=.+' .env 2>/dev/null; then
  echo "==> DeepSeek: синхронизация answer-промптов в БД"
  $COMPOSE exec -T backend python scripts/sync_provider_answer_prompts.py deepseek --apply || true
fi
if grep -qE '^ANTHROPIC_API_KEY=.+' .env 2>/dev/null; then
  echo "==> Claude: синхронизация answer-промптов в БД (отдельно от DeepSeek)"
  $COMPOSE exec -T backend python scripts/sync_provider_answer_prompts.py anthropic_claude --apply || true
fi

echo "==> Health checks (127.0.0.1:${PROXY_PORT})"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PROXY_PORT}/api/health" -H "Host: ${API_HOST_CHECK}" >/dev/null 2>&1; then
    echo "    API OK"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "    API FAIL — $COMPOSE logs backend --tail 40"
    exit 1
  fi
  sleep 2
done

APP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PROXY_PORT}/" -H "Host: ${APP_HOST_CHECK}" || echo "000")
ADMIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PROXY_PORT}/login" -H "Host: ${ADMIN_HOST_CHECK}" || echo "000")
ADMIN_TITLE=$(curl -s "http://127.0.0.1:${PROXY_PORT}/login" -H "Host: ${ADMIN_HOST_CHECK}" | grep -oi '<title>[^<]*</title>' | head -1 || true)

APP_HTML=$(curl -sf "http://127.0.0.1:${PROXY_PORT}/" -H "Host: ${APP_HOST_CHECK}" 2>/dev/null || true)
APP_JS=$(echo "$APP_HTML" | grep -oE '/assets/index-[^"[:space:]]+\.js' | head -1 || true)
if [ -n "$APP_JS" ]; then
  if curl -sf "http://127.0.0.1:${PROXY_PORT}${APP_JS}" -H "Host: ${APP_HOST_CHECK}" | grep -q 'composer-attach-dropdown'; then
    echo "    app bundle: attach menu OK (${APP_JS})"
  else
    echo "    WARN: app JS без меню вложений — пересоберите frontend: $COMPOSE build --no-cache frontend && $COMPOSE up -d --force-recreate frontend nginx"
  fi
else
  echo "    WARN: не удалось найти /assets/index-*.js в index.html"
fi

echo "    app (${APP_HOST_CHECK}): HTTP ${APP_CODE}"
echo "    admin (${ADMIN_HOST_CHECK}): HTTP ${ADMIN_CODE} ${ADMIN_TITLE}"

if echo "${ADMIN_TITLE:-}" | grep -qi Glosix; then
  echo "ERROR: admin отдаёт frontend (Glosix) — проверьте server_name admin в nginx.prod.conf"
  exit 1
fi

$COMPOSE ps
echo "==> Update complete"
