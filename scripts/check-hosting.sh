#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ok() { echo -e "${GREEN}OK${NC} $*"; }
fail() { echo -e "${RED}FAIL${NC} $*"; ERR=1; }

ERR=0

[ -f .env ] && ok ".env exists" || fail ".env missing — run configure-hosting.sh"
[ -f nginx/nginx.prod.conf ] && ok "nginx.prod.conf exists" || fail "nginx.prod.conf missing"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
  grep -q CHANGE_ME .env 2>/dev/null && fail ".env has CHANGE_ME placeholders" || ok ".env secrets set"
  [ -n "${BOT_TOKEN:-}" ] && ok "BOT_TOKEN set" || fail "BOT_TOKEN empty (required for production)"
fi

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
  for h in "$APP_HOST" "$API_HOST" "$ADMIN_HOST"; do
    ip="$(dig +short "$h" 2>/dev/null | tail -1)"
    if [ -n "$ip" ]; then ok "DNS $h -> $ip"; else fail "DNS $h not resolved"; fi
  done
fi

if docker compose -f docker-compose.prod.yml ps >/dev/null 2>&1; then
  docker compose -f docker-compose.prod.yml ps --format 'table {{.Name}}\t{{.Status}}' | tail -n +2 | while read -r line; do
    echo "  $line"
  done
  if [ -n "${API_HOST:-}" ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PROXY_PORT:-8080}/health" -H "Host: $API_HOST" 2>/dev/null || echo 000)"
    [ "$code" = "200" ] && ok "Local health via proxy ($code)" || fail "Local health check ($code)"
  fi
else
  fail "Docker stack not running"
fi

[ "$ERR" = "0" ] && echo "" && ok "All checks passed" || { echo ""; fail "Fix issues above"; exit 1; }
