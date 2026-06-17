"""Управление сессионными тредами Личного ассистента (30-минутная пауза = новый тред)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thread import Thread, ThreadType
from app.models.user import User

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 60  # 30 минут


def _redis_key(user_id: uuid.UUID, agent_id: uuid.UUID) -> str:
    return f"asst_session:{user_id}:{agent_id}"


async def get_or_create_session_thread(
    db: AsyncSession,
    redis_client,
    *,
    user: User,
    agent_id: uuid.UUID,
) -> Thread:
    """
    Возвращает текущий сессионный тред или создаёт новый.
    Новый тред создаётся если прошло > 30 минут с последнего сообщения.
    """
    key = _redis_key(user.id, agent_id)

    # Проверяем Redis
    try:
        raw = await redis_client.get(key)
        if raw:
            data = json.loads(raw)
            thread_id_str = data.get("thread_id")
            last_ts = float(data.get("ts", 0))
            if time.time() - last_ts < SESSION_TTL_SECONDS and thread_id_str:
                # Ищем тред в БД
                result = await db.execute(
                    select(Thread).where(
                        Thread.id == uuid.UUID(thread_id_str),
                        Thread.user_id == user.id,
                        Thread.deleted_at.is_(None),
                    )
                )
                thread = result.scalar_one_or_none()
                if thread:
                    return thread
    except Exception as exc:
        logger.warning("session_thread: redis read error: %s", exc)

    # Создаём новый тред
    thread = await _create_session_thread(db, user=user)
    await _save_session(redis_client, user.id, agent_id, thread.id)
    return thread


async def _create_session_thread(db: AsyncSession, *, user: User) -> Thread:
    now = datetime.now(timezone.utc)
    title = f"Личный ассистент · {now.strftime('%d %b %H:%M')}"
    thread = Thread(
        user_id=user.id,
        title=title,
        thread_type=ThreadType.SEARCH,
        message_count=0,
        last_message_at=now,
    )
    db.add(thread)
    await db.flush()
    return thread


async def touch_session(
    redis_client,
    *,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    thread_id: uuid.UUID,
) -> None:
    """Обновляет timestamp сессии после каждого сообщения."""
    await _save_session(redis_client, user_id, agent_id, thread_id)


async def _save_session(
    redis_client,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    thread_id: uuid.UUID,
) -> None:
    key = _redis_key(user_id, agent_id)
    data = json.dumps({"thread_id": str(thread_id), "ts": time.time()})
    try:
        await redis_client.set(key, data, ex=SESSION_TTL_SECONDS + 60)
    except Exception as exc:
        logger.warning("session_thread: redis write error: %s", exc)


async def clear_session(
    redis_client,
    *,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> None:
    """Сбрасывает сессию — следующее сообщение создаст новый тред (/new)."""
    key = _redis_key(user_id, agent_id)
    try:
        await redis_client.delete(key)
    except Exception as exc:
        logger.warning("session_thread: redis delete error: %s", exc)
