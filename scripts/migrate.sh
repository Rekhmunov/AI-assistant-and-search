#!/usr/bin/env bash
# Миграции на проде — только через docker-compose.prod.yml (тот же DATABASE_URL, что у backend).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env ]; then
  echo "ERROR: .env not found in $ROOT"
  exit 1
fi

# shellcheck disable=SC1091
source .env
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  echo "ERROR: POSTGRES_PASSWORD is empty in .env"
  exit 1
fi

echo "==> alembic upgrade head (prod backend)"
$COMPOSE exec -T backend alembic upgrade head
echo "==> current revision:"
$COMPOSE exec -T backend alembic current
