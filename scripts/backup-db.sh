#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/aisearch_${STAMP}.sql.gz"

# shellcheck disable=SC1091
[ -f .env ] && source .env

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-aisearch}"

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILE"

echo "Backup: $FILE ($(du -h "$FILE" | cut -f1))"

# Удалить бэкапы старше 14 дней
find "$BACKUP_DIR" -name 'aisearch_*.sql.gz' -mtime +14 -delete 2>/dev/null || true
