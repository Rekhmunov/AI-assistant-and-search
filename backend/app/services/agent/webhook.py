"""Обработка MAX webhook для агентов."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.services.agent.moderation import handle_group_moderation
from app.services.agent.profile import group_setup_roles

logger = logging.getLogger(__name__)


def parse_chat_id(payload: dict[str, Any]) -> int | None:
    for key in ("chat_id",):
        raw = payload.get(key)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.lstrip("-").isdigit():
            return int(raw)
    chat = payload.get("chat")
    if isinstance(chat, dict):
        raw = chat.get("chat_id") or chat.get("id")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.lstrip("-").isdigit():
            return int(raw)
    message = payload.get("message")
    if isinstance(message, dict):
        recipient = message.get("recipient")
        if isinstance(recipient, dict):
            raw = recipient.get("chat_id") or recipient.get("id")
            if isinstance(raw, int):
                return raw
    return None


def _message_obj(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    return message if isinstance(message, dict) else None


def message_text(payload: dict[str, Any]) -> str:
    message = _message_obj(payload)
    if not message:
        return ""
    body = message.get("body")
    if isinstance(body, dict) and body.get("text"):
        return str(body["text"])
    if message.get("text"):
        return str(message["text"])
    return ""


def message_id(payload: dict[str, Any]) -> str | None:
    message = _message_obj(payload)
    if not message:
        return None
    body = message.get("body")
    if isinstance(body, dict):
        for key in ("mid", "message_id", "id"):
            raw = body.get(key)
            if raw is not None:
                return str(raw)
    for key in ("mid", "message_id", "id"):
        raw = message.get(key)
        if raw is not None:
            return str(raw)
    return None


def message_author(payload: dict[str, Any]) -> str:
    message = _message_obj(payload)
    if not message:
        return "?"
    sender = message.get("sender") or message.get("from")
    if isinstance(sender, dict):
        if sender.get("is_bot") or sender.get("isBot"):
            return "bot"
        return str(sender.get("name") or sender.get("username") or sender.get("user_id") or "?")
    return "?"


def is_bot_sender(payload: dict[str, Any]) -> bool:
    message = _message_obj(payload)
    if not message:
        return False
    sender = message.get("sender") or message.get("from")
    if isinstance(sender, dict):
        return bool(sender.get("is_bot") or sender.get("isBot"))
    return False


def is_direct_message(payload: dict[str, Any]) -> bool:
    """Личное сообщение боту (нет group chat_id или chat_type dialog)."""
    chat_id = parse_chat_id(payload)
    if chat_id is None:
        return True
    chat = payload.get("chat")
    if isinstance(chat, dict):
        ctype = str(chat.get("type") or chat.get("chat_type") or "").lower()
        if ctype in {"dialog", "private", "user"}:
            return True
    message = _message_obj(payload)
    if isinstance(message, dict):
        recipient = message.get("recipient")
        if isinstance(recipient, dict):
            ctype = str(recipient.get("type") or recipient.get("chat_type") or "").lower()
            if ctype in {"dialog", "private", "user"}:
                return True
    return False


def is_bot_added(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    return update_type in {"bot_added", "bot.added"} or payload.get("event") == "bot_added"


def is_bot_removed(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    return update_type in {"bot_removed", "bot.removed"} or payload.get("event") == "bot_removed"


def is_message_created(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    return update_type in {"message_created", "message.created"} or payload.get("event") == "message_created"


def _bind_chat_to_agent(agent: AgentInstance, chat_id: int) -> None:
    cfg = dict(agent.config or {})
    cfg["registered_group_chat_id"] = chat_id
    agent.config = cfg
    if not agent.max_chat_id:
        agent.max_chat_id = chat_id


async def register_group_chat_for_user(
    db: AsyncSession,
    *,
    max_user_id: int,
    chat_id: int,
    include_active: bool = True,
) -> None:
    statuses = [AgentStatus.DRAFT.value, AgentStatus.COLLECTING.value]
    if include_active:
        statuses.append(AgentStatus.ACTIVE.value)

    roles = group_setup_roles()
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status.in_(statuses),
            AgentInstance.role.in_(roles),
        )
    )
    agents = result.scalars().all()
    for agent in agents:
        _bind_chat_to_agent(agent, chat_id)

    result_dm = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status.in_(statuses),
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
        )
    )
    for agent in result_dm.scalars().all():
        scope = str((agent.config or {}).get("scope") or "").lower()
        if scope in {"group", "both"}:
            _bind_chat_to_agent(agent, chat_id)

    result2 = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status.in_(statuses),
            AgentInstance.role.in_([AgentRole.NEWS_DIGEST.value, AgentRole.IMAGE_POST.value]),
        )
    )
    for agent in result2.scalars().all():
        cfg = agent.config if isinstance(agent.config, dict) else {}
        if str(cfg.get("delivery_mode") or "").lower() == "group":
            _bind_chat_to_agent(agent, chat_id)


async def handle_bot_removed_from_chat(
    db: AsyncSession,
    *,
    chat_id: int,
) -> int:
    """Помечает агентов, привязанных к чату, что бот удалён из группы."""
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_chat_id == chat_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    updated = 0
    for agent in result.scalars().all():
        cfg = dict(agent.config or {})
        cfg["bot_removed_from_chat"] = True
        cfg["bot_removed_at"] = datetime.now(timezone.utc).isoformat()
        cfg["last_dispatch_explanation"] = (
            f"Бот удалён из чата {chat_id}. Добавьте Glosix в группу снова."
        )
        agent.config = cfg
        updated += 1
    return updated


async def append_group_message(
    db: AsyncSession,
    *,
    chat_id: int,
    text: str,
    author: str,
    message_id_value: str | None = None,
) -> int:
    if not text.strip() or author == "bot":
        return 0
    updated = 0

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.GROUP_MESSAGE_LOG.value,
            AgentInstance.max_chat_id == chat_id,
        )
    )
    for agent in result.scalars().all():
        cfg = dict(agent.config or {})
        buffer = list(cfg.get("message_buffer") or [])
        buffer.append(
            {
                "author": author,
                "text": text[:1000],
                "at": datetime.now(timezone.utc).isoformat(),
                "message_id": message_id_value,
            }
        )
        cfg["message_buffer"] = buffer[-80:]
        agent.config = cfg
        updated += 1

    mod_result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.GROUP_MODERATION.value,
            AgentInstance.max_chat_id == chat_id,
        )
    )
    for agent in mod_result.scalars().all():
        await handle_group_moderation(
            db,
            agent,
            message_id=message_id_value,
            text=text,
            author=author,
            chat_id=chat_id,
        )
        updated += 1

    return updated
