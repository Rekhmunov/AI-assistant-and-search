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
  NGINX_BACKUP=""
  if [ -f nginx/nginx.prod.conf ] && ! git diff --quiet -- nginx/nginx.prod.conf 2>/dev/null; then
    NGINX_BACKUP="nginx/nginx.prod.conf.bak.$(date +%Y%m%d_%H%M%S)"
    cp -f nginx/nginx.prod.conf "$NGINX_BACKUP"
    echo "==> Локальный nginx/nginx.prod.conf — копия: $NGINX_BACKUP"
    echo "==> Временно откладываем для git pull"
    git stash push -m "update.sh: prod nginx.prod.conf" -- nginx/nginx.prod.conf && NGINX_STASHED=1 || {
      git checkout -- nginx/nginx.prod.conf 2>/dev/null || git restore nginx/nginx.prod.conf 2>/dev/null || true
    }
  fi

  sync_git_with_origin() {
    local ahead behind
    ahead="$(git rev-list --count "origin/${BRANCH}"..HEAD 2>/dev/null || echo 0)"
    behind="$(git rev-list --count HEAD.."origin/${BRANCH}" 2>/dev/null || echo 0)"

    if git pull --ff-only origin "$BRANCH"; then
      return 0
    fi

    if [ "${ahead:-0}" -gt 0 ]; then
      echo "==> Локальный main разошёлся с GitHub (локально +${ahead}, на origin +${behind:-0})"
      echo "==> На проде принимаем origin/${BRANCH} (локальные коммиты на сервере сбрасываются)"
      git reset --hard "origin/${BRANCH}"
      return 0
    fi

    echo "ERROR: git pull не прошёл (не fast-forward). Проверьте: git status"
    echo "       Ручной сброс: git fetch origin && git reset --hard origin/${BRANCH}"
    echo "       Если конфликт nginx.prod.conf — см. docs/DEPLOY.md"
    return 1
  }

  if ! sync_git_with_origin; then
    exit 1
  fi

  if [ "$NGINX_STASHED" = 1 ]; then
    if ! git stash pop; then
      echo "WARN: stash pop конфликт — восстановите: cp ${NGINX_BACKUP:-nginx/nginx.prod.conf.bak.*} nginx/nginx.prod.conf"
      git checkout stash@{0} -- nginx/nginx.prod.conf 2>/dev/null || true
      git stash drop 2>/dev/null || true
    fi
  elif [ -n "$NGINX_BACKUP" ] && [ -f "$NGINX_BACKUP" ]; then
    cp -f "$NGINX_BACKUP" nginx/nginx.prod.conf
  fi
else
  echo "==> No .git — только update-prod"
fi

exec bash scripts/update-prod.sh
