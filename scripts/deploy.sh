#!/usr/bin/env bash
# Полный деплой на VPS: clone/update -> configure -> build -> up
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$ROOT/hosting.config" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/hosting.config"
fi

APP_DIR="${APP_DIR:-/opt/aisearch}"
REPO_URL="${REPO_URL:-https://github.com/Rekhmunov/AI-assistant-and-search.git}"
BRANCH="${GIT_BRANCH:-cursor/initial-service-scaffold-f0d8}"

echo "==> AI Search deploy -> ${APP_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Run: sudo bash scripts/install-docker.sh"
  exit 1
fi

mkdir -p "$(dirname "$APP_DIR")"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH" || true

if [ -f hosting.config ] && [ ! -f .env ]; then
  echo "==> Generating .env and nginx from hosting.config"
  bash scripts/configure-hosting.sh
fi

if [ ! -f .env ]; then
  cp .env.production.example .env
  echo "Создайте hosting.config и выполните: bash scripts/configure-hosting.sh"
  exit 1
fi

if [ ! -s nginx/nginx.prod.conf ] || grep -q "make configure" nginx/nginx.prod.conf 2>/dev/null; then
  echo "Сначала: bash scripts/configure-hosting.sh"
  exit 1
fi
if grep -q "example.com" nginx/nginx.prod.conf 2>/dev/null; then
  echo "Обновите домены: bash scripts/configure-hosting.sh"
  exit 1
fi

if grep -q "CHANGE_ME" .env 2>/dev/null; then
  echo "Заполните секреты в .env"
  exit 1
fi

docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d

echo ""
bash scripts/check-hosting.sh || true
