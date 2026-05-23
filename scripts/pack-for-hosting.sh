#!/usr/bin/env bash
# Архив для загрузки на хостинг по SFTP (без node_modules и кэшей)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
OUT="aisearch-hosting-${VERSION}.tar.gz"

echo "==> Упаковка в ${OUT}"

tar -czf "$OUT" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='admin/node_modules' \
  --exclude='frontend/dist' \
  --exclude='admin/dist' \
  --exclude='backend/.venv' \
  --exclude='__pycache__' \
  --exclude='.env' \
  --exclude='hosting.config' \
  --exclude='pgdata' \
  --exclude='*.tar.gz' \
  -C "$ROOT" \
  backend frontend admin nginx scripts docs hosting systemd \
  docker-compose.prod.yml docker-compose.yml \
  .env.production.example hosting.config.example \
  Makefile README.md

echo "==> Готово: $(du -h "$OUT" | cut -f1) — $ROOT/$OUT"
echo "На сервере:"
echo "  tar -xzf $OUT -C /opt/aisearch --strip-components=0  # или в пустую папку"
echo "  cd /opt/aisearch && cp hosting.config.example hosting.config && nano hosting.config"
echo "  bash scripts/configure-hosting.sh"
