#!/usr/bin/env bash
# Полный цикл: git pull main + update-prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GIT_BRANCH:-main}"

if [ -d .git ]; then
  echo "==> Git pull origin ${BRANCH}"
  if [ -f .git/MERGE_HEAD ] || [ -d .git/rebase-merge ]; then
    echo "==> Незавершённый merge/rebase — откатываем (nginx сохраняем в .bak)"
    cp -f nginx/nginx.prod.conf "nginx/nginx.prod.conf.pre-merge.bak" 2>/dev/null || true
    git merge --abort 2>/dev/null || true
    git rebase --abort 2>/dev/null || true
    git reset --merge 2>/dev/null || true
  fi
  git fetch origin
  git checkout "$BRANCH"

  # На старых клонах nginx.prod.conf был в git; на сервере его правят вручную — не блокируем pull.
  NGINX_STASHED=0
  if [ -f nginx/nginx.prod.conf ] && ! git diff --quiet -- nginx/nginx.prod.conf 2>/dev/null; then
    echo "==> Локальный nginx/nginx.prod.conf — временно откладываем для git pull"
    git stash push -m "update.sh: prod nginx.prod.conf" -- nginx/nginx.prod.conf && NGINX_STASHED=1 || {
      cp nginx/nginx.prod.conf "nginx/nginx.prod.conf.bak.$(date +%Y%m%d_%H%M%S)"
      git checkout -- nginx/nginx.prod.conf 2>/dev/null || git restore nginx/nginx.prod.conf 2>/dev/null || true
    }
  fi

  if ! git pull --ff-only origin "$BRANCH"; then
    echo "ERROR: git pull не прошёл. Если снова nginx.prod.conf — см. docs/DEPLOY.md"
    exit 1
  fi

  if [ "$NGINX_STASHED" = 1 ]; then
    if ! git stash pop; then
      echo "WARN: stash pop конфликт — восстановите: cp nginx/nginx.prod.conf.bak.* nginx/nginx.prod.conf"
      git checkout stash@{0} -- nginx/nginx.prod.conf 2>/dev/null || true
      git stash drop 2>/dev/null || true
    fi
  fi
else
  echo "==> No .git — только update-prod"
fi

exec bash scripts/update-prod.sh
