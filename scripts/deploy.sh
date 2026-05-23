#!/usr/bin/env bash
# Run on VPS as root or user with docker group.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/aisearch}"
REPO_URL="${REPO_URL:-https://github.com/Rekhmunov/AI-assistant-and-search.git}"
BRANCH="${BRANCH:-cursor/initial-service-scaffold-f0d8}"

echo "==> AI Search deploy to ${APP_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker first (see docs/DEPLOY.md)."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin not found."
  exit 1
fi

mkdir -p "$(dirname "$APP_DIR")"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  cd "$APP_DIR"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

cd "$APP_DIR"

if [ ! -f .env ]; then
  cp .env.production.example .env
  echo ""
  echo "Created .env from template. EDIT IT before continuing:"
  echo "  nano ${APP_DIR}/.env"
  echo "  nano ${APP_DIR}/nginx/nginx.prod.conf"
  exit 1
fi

if grep -q "example.com" nginx/nginx.prod.conf 2>/dev/null; then
  echo "WARNING: nginx/nginx.prod.conf still contains example.com — update domains first."
  exit 1
fi

if grep -q "CHANGE_ME" .env 2>/dev/null; then
  echo "WARNING: .env still has CHANGE_ME placeholders — fix secrets first."
  exit 1
fi

docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "==> Stack is up. Internal nginx: http://127.0.0.1:8080"
echo "Configure ISPmanager reverse proxy -> 127.0.0.1:8080 for each domain."
echo "Health: curl -s http://127.0.0.1:8080 -H 'Host: api.example.com'  # after DNS/nginx edit"
docker compose -f docker-compose.prod.yml ps
