"""Операционные запросы в треде агента (проверка админа, связи) без онбординга."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from datetime import datetime, timezone

from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.user import User
from app.services.agent.activity_log import append_agent_activity_log
from app.services.agent.intent_hints import _extract_max_chat_id
from app.services.agent.max_probe import probe_max_chat
from app.services.agent.agent_status import (
    STATUS_ADMIN_CHECK,
    STATUS_MAX_CHAT,
    StatusCallback,
    emit_status,
    noop_status,
)
from app.services.bot import MaxBotService


def user_wants_admin_check(text: str) -> bool:
    low = (text or "").lower()
    if not re.search(r"админ|администратор|admin", low):
        return False
    if _has_write_to_group_intent(low):
        return False
    if any(
        q in low
        for q in (
            "ты там админ",
            "ты админ",
            "бот админ",
            "админ ли",
            "ли админ",
            "являешься админ",
            "является админ",
        )
    ):
        return True
    if "?" in low and re.search(r"провер\w*", low):
        return True
    return False


def _has_write_to_group_intent(low: str) -> bool:
    return any(
        m in low
        for m in (
            "напиши",
            "напис",
            "пиши",
            "отправ",
            "пост ",
            "прямо сейчас",
            "сейчас напиши",
        )
    )


def is_operational_max_query(text: str) -> bool:
    """Запросы про MAX здесь и сейчас — не настройка нового агента."""
    low = (text or "").lower()
    if user_wants_admin_check(text):
        return True
    if _has_write_to_group_intent(low):
        return False
    if _extract_max_chat_id(text) and any(
        m in low
        for m in (
            "проверь связь",
            "проверь групп",
            "проверь чат",
            "есть ли доступ",
            "добавлен ли бот",
            "бот в группе",
        )
    ):
        return True
    return False


async def _assistant_reply(db: AsyncSession, thread: Thread, content: str) -> Message:
    msg = Message(thread_id=thread.id, role=MessageRole.ASSISTANT, content=content)
    db.add(msg)
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


def bind_chat_to_current_agent(agent: AgentInstance, chat_id: int) -> None:
    """Привязка chat_id только к агенту этого треда."""
    cid = int(chat_id)
    agent.max_chat_id = cid
    cfg = dict(agent.config or {})
    cfg["max_chat_id"] = cid
    cfg["thread_chat_id"] = cid
    agent.config = cfg


async def handle_operational_query(
    db: AsyncSession,
    user: User,
    agent: AgentInstance,
    thread: Thread,
    text: str,
    *,
    user_msg: Message,
    on_status: StatusCallback | None = None,
) -> tuple[Message, Message, AgentInstance] | None:
    """
    Быстрый ответ на проверку админа/чата в контексте текущего треда.
    Возвращает None, если запрос не операционный.
    """
    if not is_operational_max_query(text):
        return None

    chat_id = _extract_max_chat_id(text) or agent.max_chat_id
    if chat_id is None:
        assistant = await _assistant_reply(
            db,
            thread,
            "Укажите ссылку на группу MAX (web.max.ru/-ID) или добавьте бота Glosix в группу.",
        )
        await db.commit()
        return user_msg, assistant, agent

    bind_chat_to_current_agent(agent, int(chat_id))
    status_cb = on_status or noop_status
    if user_wants_admin_check(text):
        await emit_status(status_cb, STATUS_ADMIN_CHECK)
    else:
        await emit_status(status_cb, STATUS_MAX_CHAT)
    bot = MaxBotService()
    probe = await probe_max_chat(bot, int(chat_id), send_test=False)
    admin = probe.get("bot_is_admin")
    if admin is None and probe.get("ok"):
        admin = await bot.check_bot_is_group_admin(int(chat_id))

    await append_agent_activity_log(
        db,
        agent,
        "admin_check",
        details={"chat_id": int(chat_id), "probe": probe, "bot_is_admin": admin},
    )

    lines = [f"**Группа MAX:** `{chat_id}`"]
    if probe.get("title"):
        lines.append(f"**Название:** {probe['title']}")
    if probe.get("status"):
        lines.append(f"**Статус бота в чате:** {probe['status']}")

    if not probe.get("ok"):
        lines.append("")
        lines.append(probe.get("explanation") or "Не удалось получить данные о чате.")
    elif admin is True:
        lines.append("")
        lines.append("**Да — бот Glosix является администратором** этой группы.")
    elif admin is False:
        lines.append("")
        lines.append(
            "**Нет — бот в группе, но не администратор.** "
            "Для модерации и чтения всех сообщений назначьте Glosix админом в MAX."
        )
    else:
        lines.append("")
        lines.append(
            "Бот в чате, но MAX API не вернул права администратора "
            "(нужны права админа для запроса /members). "
            "Для обычных постов в группу админ часто не обязателен."
        )

    assistant = await _assistant_reply(db, thread, "\n".join(lines))
    await db.commit()
    return user_msg, assistant, agent
