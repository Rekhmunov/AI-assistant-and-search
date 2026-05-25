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

if command -v envsubst >/dev/null 2>&1; then
  export APP_HOST API_HOST ADMIN_HOST
  envsubst '${APP_HOST} ${API_HOST} ${ADMIN_HOST}' \
    < nginx/nginx.prod.conf.template > nginx/nginx.prod.conf
else
  sed -e "s/\${APP_HOST}/${APP_HOST}/g" \
      -e "s/\${API_HOST}/${API_HOST}/g" \
      -e "s/\${ADMIN_HOST}/${ADMIN_HOST}/g" \
      nginx/nginx.prod.conf.template > nginx/nginx.prod.conf
fi

echo "nginx/nginx.prod.conf updated (${APP_HOST}, ${API_HOST}, ${ADMIN_HOST})"
