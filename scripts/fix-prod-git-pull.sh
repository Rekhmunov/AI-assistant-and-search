#!/usr/bin/env bash
# Сброс зависшего merge и pull main без потери nginx.prod.conf
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP="${ROOT}/nginx/nginx.prod.conf.backup.$(date +%Y%m%d_%H%M%S)"
if [ -f nginx/nginx.prod.conf ]; then
  cp nginx/nginx.prod.conf "$BACKUP"
  echo "==> nginx backup: $BACKUP"
fi

git merge --abort 2>/dev/null || true
git rebase --abort 2>/dev/null || true
git reset --merge 2>/dev/null || true

# Снять nginx с индекса, если старый репозиторий всё ещё трекает файл
git rm -f --cached nginx/nginx.prod.conf 2>/dev/null || true

git fetch origin
git checkout main
git reset --hard origin/main

if [ -f "$BACKUP" ]; then
  cp "$BACKUP" nginx/nginx.prod.conf
  echo "==> nginx.prod.conf restored from backup"
fi

echo "==> OK. Запустите: bash scripts/update-prod.sh"
