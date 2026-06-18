"""Callback-обработчик кнопок «Личного ассистента» в MAX."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thread import Thread
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_THREAD_PREFIX = "assistant_thread:"


async def handle_assistant_callback(
    db: AsyncSession,
    redis_client,
    *,
    callback_id: str,
    payload: str,
    clicker_user_id: int | None,
) -> bool:
    """
    Обрабатывает callback кнопки треда из /history.
    Payload: 'assistant_thread:{thread_uuid}'
    Переключает сессию бота на выбранный тред и пишет подтверждение.
    """
    if not payload.startswith(_THREAD_PREFIX):
        return False
    if not clicker_user_id:
        return False

    thread_id_str = payload[len(_THREAD_PREFIX):]
    try:
        thread_id = uuid.UUID(thread_id_str)
    except ValueError:
        return False

    from app.services.agent.assistant_bot_handler import _find_active_assistant
    found = await _find_active_assistant(db, max_user_id=clicker_user_id)
    if not found:
        return False
    agent, user = found

    # Проверяем что тред принадлежит этому пользователю
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        return False

    # Переключаем сессию на выбранный тред
    from app.services.agent.session_thread import _save_session
    await _save_session(redis_client, user.id, agent.id, thread_id)

    bot = MaxBotService()
    await bot.answer_callback(callback_id, "Тред выбран")

    title = (thread.title or "Диалог")[:60]
    await bot.send_message(
        clicker_user_id,
        f"✅ Продолжаем в треде:\n**{title}**\n\nПишите — отвечу в этом контексте.",
        text_format="markdown",
    )
    return True
