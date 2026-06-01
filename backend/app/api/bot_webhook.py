import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.bot_welcome import send_bot_welcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["bot"])


def _extract_max_user_id(payload: dict[str, Any]) -> int | None:
    for key in ("user_id", "id"):
        if isinstance(payload.get(key), int):
            return payload[key]
        if isinstance(payload.get(key), str) and payload[key].isdigit():
            return int(payload[key])

    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("user_id", "id"):
            value = user.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _is_bot_started(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    if update_type in {"bot_started", "bot.started"}:
        return True
    return payload.get("event") == "bot_started"


@router.post("/webhook")
async def max_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """MAX Bot API webhook: отправляет приветствие при bot_started (/start)."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    if not isinstance(payload, dict):
        return {"ok": True}

    if not _is_bot_started(payload):
        return {"ok": True}

    max_user_id = _extract_max_user_id(payload)
    if max_user_id is None:
        logger.warning("MAX webhook bot_started without user id: %s", payload)
        return {"ok": True}

    try:
        await send_bot_welcome(db, max_user_id)
    except Exception:
        logger.exception("Failed to send bot welcome to MAX user %s", max_user_id)

    return {"ok": True}
