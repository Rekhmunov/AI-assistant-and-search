#!/usr/bin/env bash
# Генерирует .env и nginx/nginx.prod.conf из hosting.config
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG_FILE="${CONFIG_FILE:-$ROOT/hosting.config}"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Нет файла hosting.config"
  echo "  cp hosting.config.example hosting.config"
  echo "  nano hosting.config"
  exit 1
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

for var in DOMAIN APP_HOST API_HOST ADMIN_HOST; do
  if [ -z "${!var:-}" ]; then
    echo "Заполните $var в hosting.config"
    exit 1
  fi
done

PROXY_PORT="${PROXY_PORT:-8080}"
APP_DIR="${APP_DIR:-/opt/aisearch}"

gen_secret() {
  openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64
}

gen_secret_24() {
  openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | xxd -p -c 48
}

JWT_SECRET_VAL="${JWT_SECRET:-$(gen_secret)}"
ADMIN_KEY_VAL="${ADMIN_API_KEY:-$(gen_secret_24)}"
POSTGRES_PW_VAL="${POSTGRES_PASSWORD:-$(gen_secret)}"

VITE_URL="https://${API_HOST}"
CORS="https://${APP_HOST},https://${API_HOST}"

if [ -f .env ] && [ "${FORCE:-0}" != "1" ]; then
  echo ".env уже существует. Для перезаписи: FORCE=1 bash scripts/configure-hosting.sh"
  exit 1
fi

cat > .env <<EOF
# Сгенерировано scripts/configure-hosting.sh $(date -Iseconds)
PROXY_PORT=${PROXY_PORT}
ENVIRONMENT=production
DEBUG=false
SKIP_INIT_DATA_VALIDATION=false

VITE_API_URL=${VITE_URL}
CORS_ORIGINS=${CORS}

JWT_SECRET=${JWT_SECRET_VAL}
ADMIN_API_KEY=${ADMIN_KEY_VAL}
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${POSTGRES_PW_VAL}
POSTGRES_DB=aisearch

BOT_TOKEN=${BOT_TOKEN:-}

YANDEX_FOLDER_ID=${YANDEX_FOLDER_ID:-}
YANDEX_API_KEY=${YANDEX_API_KEY:-}

YOOKASSA_SHOP_ID=${YOOKASSA_SHOP_ID:-}
YOOKASSA_SECRET_KEY=${YOOKASSA_SECRET_KEY:-}

FREE_SEARCHES_PER_DAY=10
PRO_SEARCHES_PER_DAY=200
GLOBAL_YANDEX_REQUESTS_PER_DAY=5000
EOF

chmod 600 .env

render_nginx() {
  if command -v envsubst >/dev/null 2>&1; then
    export APP_HOST API_HOST ADMIN_HOST PROXY_PORT
    envsubst '${APP_HOST} ${API_HOST} ${ADMIN_HOST}' \
      < nginx/nginx.prod.conf.template > nginx/nginx.prod.conf
  else
    sed -e "s/\${APP_HOST}/${APP_HOST}/g" \
        -e "s/\${API_HOST}/${API_HOST}/g" \
        -e "s/\${ADMIN_HOST}/${ADMIN_HOST}/g" \
        nginx/nginx.prod.conf.template > nginx/nginx.prod.conf
  fi
}
render_nginx

echo "==> Создано:"
echo "    .env"
echo "    nginx/nginx.prod.conf"
echo ""
echo "Домены:"
echo "    Миниапп (MAX): https://${APP_HOST}"
echo "    API:           https://${API_HOST}"
echo "    Admin:         https://${ADMIN_HOST}"
echo ""
echo "Дальше:"
echo "    1) Пропишите BOT_TOKEN и Yandex-ключи в .env (если нужно)"
echo "    2) DNS A-записи -> IP сервера"
echo "    3) docker compose -f docker-compose.prod.yml up -d --build"
echo "    4) ISPmanager -> proxy на 127.0.0.1:${PROXY_PORT}"
