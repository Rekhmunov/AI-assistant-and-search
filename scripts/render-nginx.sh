#!/usr/bin/env bash
# Regenerate nginx/nginx.prod.conf from hosting.config (does not touch .env).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG="${CONFIG_FILE:-$ROOT/hosting.config}"
if [ ! -f "$CONFIG" ]; then
  echo "hosting.config not found — skip nginx render"
  exit 0
fi

# shellcheck disable=SC1090
source "$CONFIG"

for var in APP_HOST API_HOST ADMIN_HOST; do
  if [ -z "${!var:-}" ]; then
    echo "hosting.config: fill $var"
    exit 1
  fi
done

if [ ! -f nginx/nginx.prod.conf.template ]; then
  echo "nginx/nginx.prod.conf.template missing"
  exit 1
fi

APP_SERVER_NAMES="${APP_HOST}"
if [ -n "${APP_HOST_ALIASES:-}" ]; then
  APP_SERVER_NAMES="${APP_SERVER_NAMES} ${APP_HOST_ALIASES}"
fi

_render_main() {
  if command -v envsubst >/dev/null 2>&1; then
    export APP_SERVER_NAMES API_HOST ADMIN_HOST
    envsubst '${APP_SERVER_NAMES} ${API_HOST} ${ADMIN_HOST}' \
      < nginx/nginx.prod.conf.template
  else
    sed -e "s/\${APP_SERVER_NAMES}/${APP_SERVER_NAMES}/g" \
        -e "s/\${API_HOST}/${API_HOST}/g" \
        -e "s/\${ADMIN_HOST}/${ADMIN_HOST}/g" \
        nginx/nginx.prod.conf.template
  fi
}

_render_main > nginx/nginx.prod.conf

if [ -n "${LEGACY_APP_HOST:-}" ]; then
  cat >> nginx/nginx.prod.conf <<EOF

server {
    listen 80;
    server_name ${LEGACY_APP_HOST};

    return 301 https://${APP_HOST}\$request_uri;
}
EOF
fi

echo "nginx/nginx.prod.conf updated (${APP_SERVER_NAMES}, ${API_HOST}, ${ADMIN_HOST})"
