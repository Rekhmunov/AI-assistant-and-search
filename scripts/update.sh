#!/usr/bin/env bash
# Полный цикл: git pull main + update-prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GIT_BRANCH:-main}"

if [ -d .git ]; then
  echo "==> Git pull origin ${BRANCH}"
  git fetch origin
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "==> No .git — только update-prod"
fi

exec bash scripts/update-prod.sh
