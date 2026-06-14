"""Фоновая обработка MAX webhook — ответ 200 в течение 30 с (POST /subscriptions)."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.services.agent.dm_commands import handle_dm_message
from app.services.agent.webhook import append_group_message

logger = logging.getLogger(__name__)


async def process_dm_message_background(
    *,
    max_user_id: int,
    text: str,
    payload: dict | None = None,
    message_id_value: str | None = None,
) -> None:
    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with async_session_factory() as db:
            handled = await handle_dm_message(
                db,
                redis_client,
                max_user_id=max_user_id,
                text=text,
                payload=payload,
                message_id_value=message_id_value,
            )
            if handled:
                await db.commit()
    except Exception:
        logger.exception("MAX webhook DM background failed user=%s", max_user_id)
    finally:
        await redis_client.aclose()


async def process_group_message_background(
    *,
    chat_id: int,
    text: str,
    author: str,
    message_id_value: str | None,
    payload: dict | None = None,
) -> None:
    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with async_session_factory() as db:
            from app.services.agent.group_interactive import handle_group_interactive
            from app.services.agent.max_media import transcribe_voice_message

            effective_text = text
            if not effective_text and payload:
                voice_text = await transcribe_voice_message(payload)
                if voice_text:
                    effective_text = voice_text
                    logger.info("Group voice transcribed chat_id=%s len=%s", chat_id, len(voice_text))

            interactive = await handle_group_interactive(
                db,
                redis_client,
                chat_id=chat_id,
                text=effective_text,
                author=author,
                payload=payload or {},
                message_id_value=message_id_value,
            )
            count = await append_group_message(
                db,
                chat_id=chat_id,
                text=text,
                author=author,
                message_id_value=message_id_value,
            )
            if interactive or count:
                await db.commit()
    except Exception:
        logger.exception("MAX webhook group background failed chat=%s", chat_id)
    finally:
        await redis_client.aclose()


async def process_callback_background(
    *,
    callback_id: str,
    callback_payload: str,
    clicker_user_id: int | None = None,
) -> None:
    """
    Обрабатывает нажатие inline-кнопки (message_callback).
    ВСЕГДА вызывает answer_callback — иначе кнопка висит в loading вечно.
    """
    from app.services.bot import MaxBotService
    bot = MaxBotService()
    try:
        if callback_payload.startswith("secretary:"):
            async with async_session_factory() as db:
                from app.services.agent.secretary_callbacks import handle_secretary_callback
                handled = await handle_secretary_callback(
                    db,
                    callback_id=callback_id,
                    payload=callback_payload,
                    clicker_user_id=clicker_user_id,
                )
                if handled:
                    await db.commit()
        else:
            # Неизвестный payload — всё равно отвечаем чтобы снять spinner с кнопки
            await bot.answer_callback(callback_id)
    except Exception:
        logger.exception("MAX webhook callback background failed callback_id=%s", callback_id)
        try:
            await bot.answer_callback(callback_id)
        except Exception:
            pass
