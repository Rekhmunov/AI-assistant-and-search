"""Безопасность инструментов агента MAX."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.models.user import User

MAX_MESSAGE_TEXT_LEN = 4000
MAX_TOOL_CALLS_PER_TURN = 12
MAX_ORCHESTRATOR_ITERATIONS = 8

ALLOWED_TOOLS = frozenset(
    {
        "max_probe_chat",
        "max_send_test",
        "max_get_chat",
        "max_list_bot_chats",
        "max_resolve_channel_link",
        "max_read_activity_logs",
        "web_search",
        "read_thread_summary",
    }
)

# Инструменты, меняющие состояние снаружи Glosix — только с явным флагом
DESTRUCTIVE_TOOLS = frozenset({"max_send_test"})


class AgentSecurityError(ValueError):
    pass


async def allowed_chat_ids_for_user(db: AsyncSession, user_id: UUID) -> set[int]:
    result = await db.execute(select(AgentInstance).where(AgentInstance.user_id == user_id))
    ids: set[int] = set()
    for agent in result.scalars().all():
        if agent.max_chat_id:
            ids.add(int(agent.max_chat_id))
        cfg = agent.config if isinstance(agent.config, dict) else {}
        for key in ("registered_group_chat_id", "max_chat_id"):
            raw = cfg.get(key)
            if raw is not None:
                try:
                    ids.add(int(raw))
                except (TypeError, ValueError):
                    pass
    return ids


def chat_id_allowed(chat_id: int, agent: AgentInstance, user: User, extra_allowed: set[int]) -> bool:
    cid = int(chat_id)
    allowed = set(extra_allowed)
    if agent.max_chat_id:
        allowed.add(int(agent.max_chat_id))
    cfg = agent.config if isinstance(agent.config, dict) else {}
    for key in ("registered_group_chat_id", "max_chat_id"):
        raw = cfg.get(key)
        if raw is not None:
            try:
                allowed.add(int(raw))
            except (TypeError, ValueError):
                pass
    return cid in allowed


def sanitize_message_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise AgentSecurityError("empty_message")
    if len(cleaned) > MAX_MESSAGE_TEXT_LEN:
        raise AgentSecurityError("message_too_long")
    return cleaned


def normalize_channel_link(link: str) -> str:
    raw = (link or "").strip()
    if not raw or len(raw) > 512:
        raise AgentSecurityError("invalid_link")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", raw):
        raise AgentSecurityError("invalid_link")
    return raw


def validate_tool_call(
    tool: str,
    args: dict[str, Any],
    *,
    agent: AgentInstance,
    user: User,
    allowed_chats: set[int],
    allow_test_send: bool,
) -> dict[str, Any]:
    name = str(tool or "").strip().lower()
    if name not in ALLOWED_TOOLS:
        raise AgentSecurityError(f"tool_not_allowed:{name}")

    payload = dict(args or {}) if isinstance(args, dict) else {}

    if name in {"max_probe_chat", "max_get_chat", "max_send_test"}:
        chat_id = payload.get("chat_id")
        if chat_id is None:
            chat_id = agent.max_chat_id
        if chat_id is None:
            raise AgentSecurityError("chat_id_required")
        cid = int(chat_id)
        if not chat_id_allowed(cid, agent, user, allowed_chats):
            raise AgentSecurityError("chat_id_forbidden")
        payload["chat_id"] = cid

    if name == "max_send_test" and not allow_test_send:
        raise AgentSecurityError("test_send_not_allowed")

    if name == "max_resolve_channel_link":
        payload["link"] = normalize_channel_link(str(payload.get("link") or ""))

    if name == "web_search":
        query = str(payload.get("query") or "").strip()
        if not query or len(query) > 500:
            raise AgentSecurityError("invalid_search_query")
        payload["query"] = query

    return payload


def user_consented_test_send(user_text: str, checklist_allow: bool = False) -> bool:
    if checklist_allow:
        return True
    low = (user_text or "").lower()
    markers = (
        "проверь связь",
        "тестовое сообщение",
        "пробное сообщение",
        "отправь тест",
        "проверь группу",
        "проверь чат",
        "probe",
        "test send",
    )
    return any(m in low for m in markers)
