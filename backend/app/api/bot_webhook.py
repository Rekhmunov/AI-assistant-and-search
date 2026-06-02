import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.services.bot_welcome import send_bot_welcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["bot"])


def _parse_user_id(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _user_id_from_user_obj(user: Any) -> int | None:
    if not isinstance(user, dict):
        return None
    uid = _parse_user_id(user.get("user_id"))
    if uid is not None:
        return uid
    return _parse_user_id(user.get("id"))


def _extract_max_user_id(payload: dict[str, Any]) -> int | None:
    uid = _parse_user_id(payload.get("user_id"))
    if uid is not None:
        return uid

    uid = _user_id_from_user_obj(payload.get("user"))
    if uid is not None:
        return uid

    inner = payload.get("payload")
    if isinstance(inner, dict):
        uid = _parse_user_id(inner.get("user_id"))
        if uid is not None:
            return uid
        uid = _user_id_from_user_obj(inner.get("user"))
        if uid is not None:
            return uid

    for key in ("id",):
        uid = _parse_user_id(payload.get(key))
        if uid is not None:
            return uid
    return None


def _is_bot_started(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    if update_type in {"bot_started", "bot.started"}:
        return True
    return payload.get("event") == "bot_started"


def _verify_webhook_secret(
    x_max_bot_api_secret: str | None,
    x_webhook_secret: str | None,
    query_secret: str | None,
) -> None:
    settings = get_settings()
    expected = settings.max_bot_webhook_secret.strip()
    # MAX official header: X-Max-Bot-Api-Secret (see POST /subscriptions)
    provided = (x_max_bot_api_secret or x_webhook_secret or query_secret or "").strip()
    if settings.environment.strip().lower() == "production":
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook not configured",
            )
        if provided != expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return
    if expected and provided != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/webhook")
async def max_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_max_bot_api_secret: Annotated[str | None, Header(alias="X-Max-Bot-Api-Secret")] = None,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    secret: Annotated[str | None, Query()] = None,
):
    """MAX Bot API webhook: отправляет приветствие при bot_started (/start)."""
    _verify_webhook_secret(x_max_bot_api_secret, x_webhook_secret, secret)
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

    sent = await send_bot_welcome(db, max_user_id)
    if not sent:
        logger.warning("Welcome not delivered to MAX user %s (check BOT_TOKEN / logs)", max_user_id)

    return {"ok": True}
