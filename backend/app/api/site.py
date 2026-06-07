from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as redis

from app.api.deps import get_db, get_redis
from app.core.config import get_settings
from app.services.app_settings import get_setting

router = APIRouter(tags=["site"])

_WEBMASTER_HTML = """<!DOCTYPE html>
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    </head>
    <body>Verification: {code}</body>
</html>"""


@router.get("/yandex_{code}.html", response_class=HTMLResponse)
async def yandex_webmaster_verification(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    """Файл верификации Яндекс.Вебмастера (HTML-метод)."""
    settings = get_settings()
    stored = str(await get_setting("yandex_webmaster_verification", db, redis_client, settings)).strip().lower()
    if not stored or code.strip().lower() != stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return HTMLResponse(
        _WEBMASTER_HTML.format(code=stored),
        headers={"Cache-Control": "no-store"},
    )
