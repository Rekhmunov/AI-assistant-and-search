#!/usr/bin/env bash
# Проверка Yandex Search + GPT на сервере или локально.
# Usage: ./scripts/test-yandex.sh [BASE_URL]
# Example: ./scripts/test-yandex.sh https://app.glosix.ru

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
echo "=== /api/health/yandex (может занять до 30 с) ==="
curl "${CURL_OPTS[@]}" --max-time 60 "$BASE/api/health/yandex" | python3 -m json.tool 2>/dev/null || curl "${CURL_OPTS[@]}" "$BASE/api/health/yandex"
echo ""
