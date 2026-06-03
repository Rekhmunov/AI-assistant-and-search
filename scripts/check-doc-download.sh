#!/usr/bin/env bash
# Проверка скачивания сгенерированного .docx через HTTP (на VPS после update).
# Без аргументов — берёт share_url из последнего сообщения с вложением-документом.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"
PROXY_PORT="${PROXY_PORT:-18080}"
APP_HOST="${APP_HOST:-glosix.ru}"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
  PROXY_PORT="${PROXY_PORT:-18080}"
  APP_HOST="${APP_HOST:-$APP_HOST}"
fi

SHARE_PATH="${1:-}"

if [ -z "$SHARE_PATH" ]; then
  echo "==> Последний generated_doc в БД (share_url из attachments)"
  SHARE_PATH="$($COMPOSE exec -T backend python - <<'PY'
import asyncio
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_factory
from app.models.message import Message

async def main() -> None:
    async with async_session_factory() as db:
        r = await db.execute(
            select(Message.attachments)
            .where(Message.attachments.isnot(None))
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        for (att,) in r.all():
            if not att:
                continue
            items = att if isinstance(att, list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("kind") == "document" and item.get("share_url"):
                    print(str(item["share_url"]).strip())
                    return
    print("", end="")

asyncio.run(main())
PY
)"
fi

SHARE_PATH="${SHARE_PATH#"${SHARE_PATH%%[![:space:]]*}"}"
SHARE_PATH="${SHARE_PATH%"${SHARE_PATH##*[![:space:]]}"}"

if [ -z "$SHARE_PATH" ]; then
  echo "ERROR: нет share_url. Сгенерируйте документ в UI или передайте путь:"
  echo "  bash scripts/check-doc-download.sh '/api/files/<uuid>/shared?token=...'"
  exit 1
fi

if [[ "$SHARE_PATH" != /* ]]; then
  SHARE_PATH="/${SHARE_PATH}"
fi

OUT="$(mktemp /tmp/glosix-doc-XXXXXX.docx)"
trap 'rm -f "$OUT"' EXIT

LOCAL_URL="http://127.0.0.1:${PROXY_PORT}${SHARE_PATH}"
PUBLIC_URL="https://${APP_HOST}${SHARE_PATH}"

echo "==> GET (docker nginx) ${LOCAL_URL}"
HTTP_LOCAL=$(curl -sS -o "$OUT" -w "%{http_code}" -H "Host: ${APP_HOST}" "$LOCAL_URL" || echo "000")
echo "    HTTP ${HTTP_LOCAL}, bytes $(wc -c <"$OUT" | tr -d ' ')"

if [ "$HTTP_LOCAL" != "200" ]; then
  echo "==> Повтор с публичного хоста ${PUBLIC_URL}"
  HTTP_PUB=$(curl -sS -o "$OUT" -w "%{http_code}" "$PUBLIC_URL" || echo "000")
  echo "    HTTP ${HTTP_PUB}, bytes $(wc -c <"$OUT" | tr -d ' ')"
  if [ "$HTTP_PUB" != "200" ]; then
    head -c 200 "$OUT" | tr '\n' ' '
    echo ""
    exit 1
  fi
fi

SIG=$(head -c 2 "$OUT" | xxd -p 2>/dev/null || od -An -tx1 -N2 "$OUT" | tr -d ' ')
if [ "$SIG" != "504b" ]; then
  echo "ERROR: ответ не похож на .docx (ожидали PK/504b, получили ${SIG:-?})"
  head -c 300 "$OUT"
  echo ""
  exit 1
fi

echo "OK: файл Word скачан ($(wc -c <"$OUT" | tr -d ' ') байт, сигнатура PK)"
