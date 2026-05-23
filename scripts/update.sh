#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi

BRANCH="${GIT_BRANCH:-main}"

echo "==> Backup DB before update"
bash scripts/backup-db.sh || echo "Backup skipped (first run?)"

if [ -d .git ]; then
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

docker compose -f docker-compose.prod.yml ps
echo "==> Update complete"
