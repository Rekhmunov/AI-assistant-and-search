import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.services.agent.webhook import (
    handle_bot_removed_from_chat,
    is_bot_added,
    is_bot_removed,
    is_bot_sender,
    is_direct_message,
    is_message_created,
    message_author,
    message_id,
    message_text,
    parse_chat_id,
    register_group_chat_for_user,
)
from app.services.agent.webhook_tasks import (
    process_dm_message_background,
    process_group_message_background,
    process_callback_background,
)
from app.services.bot_welcome import send_bot_welcome

logger = logging.getLogger(__name__)

_bot_username_initialized = False
_bot_username_lock = asyncio.Lock()


async def _ensure_bot_username_loaded() -> None:
    """Лениво загружает username бота из GET /me при первом вызове."""
    global _bot_username_initialized
    if _bot_username_initialized:
        return
    async with _bot_username_lock:
        if _bot_username_initialized:
            return
        try:
            from app.services.bot import MaxBotService
            from app.services.agent.interaction import configure_bot_username

            info = await MaxBotService().get_me()
            if info:
                username = info.get("username") or info.get("name") or ""
                if username:
                    configure_bot_username(username)
                    logger.info("Bot username set: %s", username)
        except Exception as exc:
            logger.warning("Failed to load bot username: %s", exc)
        _bot_username_initialized = True

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
    provided = (x_max_bot_api_secret or x_webhook_secret or query_secret or "").strip()

    # Секрет обязателен в любом окружении если задан.
    # В продакшне — всегда обязателен.
    from app.core.secrets import secrets_match

    if settings.environment.strip().lower() == "production":
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook not configured",
            )
        if not secrets_match(provided, expected):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return

    # Вне продакшна: если секрет задан — проверяем; если не задан — принимаем (dev/test).
    if expected and not secrets_match(provided, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/webhook")
async def max_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_max_bot_api_secret: Annotated[str | None, Header(alias="X-Max-Bot-Api-Secret")] = None,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    secret: Annotated[str | None, Query()] = None,
):
    """MAX Bot API webhook: отправляет приветствие при bot_started (/start)."""
    client_ip = request.client.host if request.client else "unknown"
    has_max_secret = bool(x_max_bot_api_secret)
    has_webhook_secret = bool(x_webhook_secret)
    has_query_secret = bool(secret)
    logger.warning(
        "WEBHOOK incoming: ip=%s has_X-Max-Bot-Api-Secret=%s has_X-Webhook-Secret=%s has_query_secret=%s",
        client_ip, has_max_secret, has_webhook_secret, has_query_secret,
    )
    try:
        _verify_webhook_secret(x_max_bot_api_secret, x_webhook_secret, secret)
    except HTTPException as exc:
        logger.warning(
            "WEBHOOK 403 Forbidden: ip=%s has_X-Max-Bot-Api-Secret=%s has_X-Webhook-Secret=%s has_query_secret=%s",
            client_ip, has_max_secret, has_webhook_secret, has_query_secret,
        )
        raise
    await _ensure_bot_username_loaded()
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    if not isinstance(payload, dict):
        return {"ok": True}

    max_user_id = _extract_max_user_id(payload)

    if _is_bot_started(payload):
        if max_user_id is None:
            logger.warning("MAX webhook bot_started without user id: %s", payload)
            return {"ok": True}
        sent = await send_bot_welcome(db, max_user_id)
        if not sent:
            logger.warning("Welcome not delivered to MAX user %s (check BOT_TOKEN / logs)", max_user_id)
        return {"ok": True}

    if is_bot_added(payload) and max_user_id is not None:
        chat_id = parse_chat_id(payload)
        if chat_id is not None:
            await register_group_chat_for_user(db, max_user_id=max_user_id, chat_id=chat_id)
            await db.commit()
        return {"ok": True}

    if is_bot_removed(payload):
        chat_id = parse_chat_id(payload)
        if chat_id is not None:
            await handle_bot_removed_from_chat(db, chat_id=chat_id)
            await db.commit()
        return {"ok": True}

    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    if update_type in {"message_callback", "message.callback"}:
        callback = payload.get("callback") or {}
        callback_id = str(callback.get("callback_id") or payload.get("callback_id") or "")
        callback_payload = str(callback.get("payload") or payload.get("payload") or "")
        if callback_id and callback_payload.startswith("secretary:"):
            background_tasks.add_task(
                process_callback_background,
                callback_id=callback_id,
                callback_payload=callback_payload,
            )
        return {"ok": True}

    if is_message_created(payload):
        if is_bot_sender(payload):
            return {"ok": True}

        text = message_text(payload)
        is_dm = is_direct_message(payload)
        chat_id = parse_chat_id(payload)
        # Полная структура payload для диагностики парсинга chat_id
        import json as _json
        msg_obj = payload.get("message") or {}
        recipient = msg_obj.get("recipient") or {}
        logger.warning(
            "WEBHOOK message_created: is_dm=%s chat_id=%s user_id=%s text_len=%s "
            "payload_keys=%s message_keys=%s recipient=%s",
            is_dm, chat_id, max_user_id, len(text or ""),
            list(payload.keys()),
            list(msg_obj.keys()),
            _json.dumps(recipient)[:200],
        )

        if is_dm and max_user_id is not None:
            background_tasks.add_task(
                process_dm_message_background,
                max_user_id=max_user_id,
                text=text,
                payload=payload,
                message_id_value=message_id(payload),
            )
            return {"ok": True}

        if chat_id is not None:
            background_tasks.add_task(
                process_group_message_background,
                chat_id=chat_id,
                text=text,
                author=message_author(payload),
                message_id_value=message_id(payload),
                payload=payload,
            )
        else:
            logger.warning("WEBHOOK message_created: could not parse chat_id from payload: %s", str(payload)[:500])
        return {"ok": True}

    return {"ok": True}
