#!/usr/bin/env bash
# Проверка, что app.glosix.ru отдаёт frontend с меню вложений.
# Usage: bash scripts/verify-prod-frontend.sh [APP_URL]

set -euo pipefail
APP_URL="${1:-https://app.glosix.ru}"
HTML=$(curl -sfL "$APP_URL/")
JS=$(echo "$HTML" | grep -oE '/assets/index-[^"[:space:]]+\.js' | head -1)
BUILD=$(echo "$HTML" | grep -oE 'data-build="[^"]+"' | head -1 || true)

echo "URL: $APP_URL"
echo "HTML build attr: ${BUILD:-not set (old index)}"
echo "JS bundle: ${JS:-NOT FOUND}"

if [ -z "$JS" ]; then
  echo "FAIL: no JS in index.html"
  exit 1
fi

BODY=$(curl -sfL "$APP_URL$JS")
if echo "$BODY" | grep -q 'composer-attach-dropdown'; then
  echo "OK: attach menu present in bundle"
else
  echo "FAIL: old bundle (no composer-attach-dropdown). Run update-prod.sh with --no-cache frontend"
  exit 1
fi

if echo "$BODY" | grep -q 'attachAdd\|Добавить файл или фото'; then
  echo "OK: new attach strings"
else
  echo "WARN: attachAdd label not found (may be minified)"
fi
