#!/usr/bin/env bash
# Проверка Yandex Search + GPT на сервере или локально.
# Usage: ./scripts/test-yandex.sh [BASE_URL]
# Example: ./scripts/test-yandex.sh https://glosix.ru

set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
HOST_HEADER="${HOST_HEADER:-}"

CURL_OPTS=(-sS)
if [[ -n "$HOST_HEADER" ]]; then
  CURL_OPTS+=(-H "Host: $HOST_HEADER")
fi

echo "=== /api/health ==="
curl "${CURL_OPTS[@]}" "$BASE/api/health" | python3 -m json.tool 2>/dev/null || curl "${CURL_OPTS[@]}" "$BASE/api/health"
echo ""
echo "=== /api/health/yandex (может занять до 30 с; нужен X-Admin-Key или admin cookie) ==="
ADMIN_HDR=()
if [[ -n "${ADMIN_API_KEY:-}" ]]; then
  ADMIN_HDR=(-H "X-Admin-Key: $ADMIN_API_KEY")
fi
curl "${CURL_OPTS[@]}" "${ADMIN_HDR[@]}" --max-time 60 "$BASE/api/health/yandex" | python3 -m json.tool 2>/dev/null || curl "${CURL_OPTS[@]}" "${ADMIN_HDR[@]}" "$BASE/api/health/yandex"
echo ""
