"""Обработка MAX webhook для групповых агентов."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus

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


def message_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        body = message.get("body")
        if isinstance(body, dict) and body.get("text"):
            return str(body["text"])
        if message.get("text"):
            return str(message["text"])
    return ""


def message_author(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if not isinstance(message, dict):
        return "?"
    sender = message.get("sender") or message.get("from")
    if isinstance(sender, dict):
        return str(sender.get("name") or sender.get("username") or sender.get("user_id") or "?")
    return "?"


def is_bot_added(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    return update_type in {"bot_added", "bot.added"} or payload.get("event") == "bot_added"


def is_message_created(payload: dict[str, Any]) -> bool:
    update_type = str(payload.get("update_type") or payload.get("type") or "").lower()
    return update_type in {"message_created", "message.created"} or payload.get("event") == "message_created"


async def register_group_chat_for_user(
    db: AsyncSession,
    *,
    max_user_id: int,
    chat_id: int,
) -> None:
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status.in_([AgentStatus.DRAFT.value, AgentStatus.COLLECTING.value]),
            AgentInstance.role.in_(
                [AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MESSAGE_LOG.value]
            ),
        )
    )
    agents = result.scalars().all()
    for agent in agents:
        cfg = dict(agent.config or {})
        cfg["registered_group_chat_id"] = chat_id
        agent.config = cfg
        if not agent.max_chat_id:
            agent.max_chat_id = chat_id


async def append_group_message(
    db: AsyncSession,
    *,
    chat_id: int,
    text: str,
    author: str,
) -> int:
    if not text.strip():
        return 0
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.GROUP_MESSAGE_LOG.value,
            AgentInstance.max_chat_id == chat_id,
        )
    )
    agents = result.scalars().all()
    updated = 0
    for agent in agents:
        cfg = dict(agent.config or {})
        buffer = list(cfg.get("message_buffer") or [])
        buffer.append(
            {
                "author": author,
                "text": text[:1000],
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        cfg["message_buffer"] = buffer[-100:]
        agent.config = cfg
        updated += 1
    return updated
