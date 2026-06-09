"""Обработка сообщений в треде агента (без поискового SSE)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import User
from app.services.agent.constants import AGENT_WELCOME
from app.services.agent.lifecycle import cancel_agent, get_agent_for_thread
from app.services.agent.onboarding import activation_summary, apply_user_message, user_wants_cancel
from app.services.agent.reminders import activate_agent_reminders
from app.services.providers.factory import resolve_runtime_providers

logger = logging.getLogger(__name__)


async def _assistant_reply(db: AsyncSession, thread: Thread, content: str) -> Message:
    msg = Message(thread_id=thread.id, role=MessageRole.ASSISTANT, content=content)
    db.add(msg)
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


async def _user_message(db: AsyncSession, thread: Thread, content: str) -> Message:
    msg = Message(thread_id=thread.id, role=MessageRole.USER, content=content)
    db.add(msg)
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


async def create_agent_thread(
    db: AsyncSession,
    user: User,
    *,
    max_user_id: int,
) -> tuple[Thread, AgentInstance, Message]:
    from app.services.thread_factory import create_thread, next_agent_seq

    seq = await next_agent_seq(db, user.id)
    title = f"Агент {seq}"
    thread = await create_thread(
        db,
        user_id=user.id,
        title=title,
        thread_type=ThreadType.AGENT,
        agent_seq=seq,
    )
    agent = AgentInstance(
        thread_id=thread.id,
        user_id=user.id,
        max_user_id=max_user_id,
        status=AgentStatus.DRAFT.value,
    )
    db.add(agent)
    await db.flush()

    welcome = await _assistant_reply(db, thread, AGENT_WELCOME)
    return thread, agent, welcome


async def handle_agent_message(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    thread_id: UUID,
    text: str,
    redis_client,
) -> tuple[Message, Message, AgentInstance]:
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise ValueError("thread_not_found")

    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise ValueError("agent_not_found")

    if agent.user_id != user.id:
        raise ValueError("agent_owner_mismatch")

    if user.max_user_id is None:
        raise ValueError("max_required")

    if agent.max_user_id != int(user.max_user_id):
        raise ValueError("max_user_mismatch")

    allowed, used, limit = await limiter.check_search_limit(str(user.id), user.plan)
    if not allowed:
        raise ValueError("rate_limit")

    user_msg = await _user_message(db, thread, text.strip())

    if user_wants_cancel(text):
        await cancel_agent(db, agent, reason="user_cancel")
        assistant = await _assistant_reply(
            db,
            thread,
            "Агент остановлен. Напоминания отменены. Создайте нового агента, если понадобится снова.",
        )
        await db.commit()
        return user_msg, assistant, agent

    if agent.status == AgentStatus.CANCELLED.value:
        assistant = await _assistant_reply(
            db,
            thread,
            "Этот агент уже отключён. Нажмите иконку робота, чтобы создать нового.",
        )
        await db.commit()
        return user_msg, assistant, agent

    if agent.status == AgentStatus.ACTIVE.value:
        assistant = await _assistant_reply(
            db,
            thread,
            (
                "Агент уже работает. "
                f"{activation_summary(agent)}\n\n"
                "Чтобы изменить параметры, отключите агента фразой «отключи агента» и создайте нового."
            ),
        )
        await db.commit()
        return user_msg, assistant, agent

    follow_up = apply_user_message(agent, text)
    if follow_up:
        assistant = await _assistant_reply(db, thread, follow_up)
        agent.status = AgentStatus.COLLECTING.value
        await db.commit()
        return user_msg, assistant, agent

    try:
        await activate_agent_reminders(db, agent)
        assistant = await _assistant_reply(db, thread, activation_summary(agent))
    except ValueError as exc:
        code = str(exc)
        if code == "schedule_unparseable":
            assistant = await _assistant_reply(
                db,
                thread,
                "Не удалось разобрать расписание. Укажите день и время, например «каждый понедельник в 10:00».",
            )
        elif code == "group_chat_missing":
            assistant = await _assistant_reply(db, thread, "Укажите ID группового чата MAX.")
        else:
            logger.warning("Agent activation failed: %s", exc)
            assistant = await _assistant_reply(db, thread, "Не хватает данных для активации. Уточните параметры.")
        await db.commit()
        return user_msg, assistant, agent
    except Exception as exc:
        logger.exception("Agent activation error")
        llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
        fallback = "Произошла ошибка при активации. Попробуйте переформулировать расписание."
        if hasattr(llm, "complete_text"):
            try:
                fallback = await llm.complete_text(  # type: ignore[attr-defined]
                    [
                        {"role": "system", "content": "Кратко объясни пользователю проблему с настройкой напоминания."},
                        {"role": "user", "content": text},
                    ],
                    model="lite",
                    max_tokens=120,
                )
            except Exception:
                pass
        assistant = await _assistant_reply(db, thread, fallback)
        await db.commit()
        return user_msg, assistant, agent

    await db.commit()
    return user_msg, assistant, agent
