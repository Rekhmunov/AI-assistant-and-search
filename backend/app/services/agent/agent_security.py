"""Безопасность инструментов агента MAX."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

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
        "max_send_file",
        "max_send_message",
        "search_thread_history",
        "store_agent_record",
        "query_agent_records",
        "update_agent_memory",
        "read_max_api_docs",
    }
)

# Инструменты, меняющие состояние снаружи Glosix — только с явным флагом
DESTRUCTIVE_TOOLS = frozenset({"max_send_test", "max_send_file", "max_send_message"})


class AgentSecurityError(ValueError):
    pass


def allowed_chat_ids_for_agent(
    agent: AgentInstance,
    *,
    message_chat_id: int | None = None,
) -> set[int]:
    """Только чаты, привязанные к агенту этого треда (+ chat_id из текущего сообщения)."""
    ids: set[int] = set()
    if agent.max_chat_id:
        ids.add(int(agent.max_chat_id))
    if agent.max_user_id:
        ids.add(int(agent.max_user_id))
    cfg = agent.config if isinstance(agent.config, dict) else {}
    for key in ("thread_chat_id", "registered_group_chat_id", "max_chat_id"):
        raw = cfg.get(key)
        if raw is not None:
            try:
                ids.add(int(raw))
            except (TypeError, ValueError):
                pass
    if message_chat_id is not None:
        ids.add(int(message_chat_id))
    return ids


def chat_id_allowed(
    chat_id: int,
    agent: AgentInstance,
    *,
    message_chat_id: int | None = None,
) -> bool:
    return int(chat_id) in allowed_chat_ids_for_agent(agent, message_chat_id=message_chat_id)


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
    message_chat_id: int | None,
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
        if not chat_id_allowed(cid, agent, message_chat_id=message_chat_id):
            raise AgentSecurityError("chat_id_forbidden")
        payload["chat_id"] = cid

    if name == "max_send_file":
        # Поддерживаем и личку (user_id) и группу (chat_id)
        raw_user_id = payload.get("user_id")
        raw_chat_id = payload.get("chat_id")
        if raw_user_id is not None:
            uid = int(raw_user_id)
            allowed_uid = int(agent.max_user_id) if agent.max_user_id else None
            if allowed_uid is None or uid != allowed_uid:
                raise AgentSecurityError("user_id_forbidden")
            payload["user_id"] = uid
            payload.pop("chat_id", None)
        else:
            if raw_chat_id is None:
                raw_chat_id = agent.max_chat_id
            if raw_chat_id is None:
                raise AgentSecurityError("chat_id_or_user_id_required")
            cid = int(raw_chat_id)
            if not chat_id_allowed(cid, agent, message_chat_id=message_chat_id):
                raise AgentSecurityError("chat_id_forbidden")
            payload["chat_id"] = cid
            payload.pop("user_id", None)

    if name == "max_send_message":
        # Поддерживаем два режима: личка (user_id) и группа (chat_id)
        raw_user_id = payload.get("user_id")
        raw_chat_id = payload.get("chat_id")
        if raw_user_id is not None:
            # Режим личных сообщений: user_id должен совпадать с владельцем агента
            uid = int(raw_user_id)
            allowed_uid = int(agent.max_user_id) if agent.max_user_id else None
            if allowed_uid is None or uid != allowed_uid:
                raise AgentSecurityError("user_id_forbidden")
            payload["user_id"] = uid
            payload.pop("chat_id", None)
        else:
            # Режим группы: chat_id обязателен и должен быть разрешён
            if raw_chat_id is None:
                raw_chat_id = agent.max_chat_id
            if raw_chat_id is None:
                raise AgentSecurityError("chat_id_or_user_id_required")
            cid = int(raw_chat_id)
            if not chat_id_allowed(cid, agent, message_chat_id=message_chat_id):
                raise AgentSecurityError("chat_id_forbidden")
            payload["chat_id"] = cid
            payload.pop("user_id", None)

    if name == "max_send_test" and not allow_test_send:
        raise AgentSecurityError("test_send_not_allowed")

    if name in {"max_send_file", "max_send_message"}:
        if not allow_test_send:
            raise AgentSecurityError("file_send_not_allowed")

    if name == "max_send_file":
        instruction = str(payload.get("instruction") or "").strip()
        if not instruction or len(instruction) > 2000:
            raise AgentSecurityError("invalid_file_instruction")
        payload["instruction"] = instruction
        fmt = str(payload.get("format") or "docx").strip().lower()
        if fmt in {"doc", "word"}:
            fmt = "docx"
        if fmt not in {"docx", "pdf", "xlsx", "image"}:
            raise AgentSecurityError("invalid_file_format")
        payload["format"] = fmt

    if name == "max_send_message":
        text = str(payload.get("text") or "").strip()
        if not text or len(text) > MAX_MESSAGE_TEXT_LEN:
            raise AgentSecurityError("invalid_message_text")
        payload["text"] = text

    if name == "search_thread_history":
        query = str(payload.get("query") or "").strip()
        if not query or len(query) > 500:
            raise AgentSecurityError("invalid_search_query")
        payload["query"] = query

    if name == "store_agent_record":
        table = str(payload.get("table") or "default").strip().lower()[:64]
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AgentSecurityError("invalid_record_data")
        payload["table"] = table
        payload["data"] = data

    if name == "query_agent_records":
        table = str(payload.get("table") or "default").strip().lower()[:64]
        payload["table"] = table
        if payload.get("category") is not None:
            payload["category"] = str(payload["category"]).strip()[:120]

    if name == "update_agent_memory":
        note = str(payload.get("note") or "").strip()
        if not note or len(note) > 500:
            raise AgentSecurityError("invalid_memory_note")
        payload["note"] = note

    if name == "max_resolve_channel_link":
        payload["link"] = normalize_channel_link(str(payload.get("link") or ""))

    if name == "web_search":
        query = str(payload.get("query") or "").strip()
        if not query or len(query) > 500:
            raise AgentSecurityError("invalid_search_query")
        payload["query"] = query

    if name == "read_max_api_docs":
        section = str(payload.get("section") or "").strip()[:200]
        payload["section"] = section

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
        "отправь файл",
        "пришли файл",
        "пришли документ",
        "отправь документ",
        "пришли pdf",
        "отправь pdf",
        "пришли excel",
        "отправь excel",
        "пришли картин",
        "отправь картин",
        "пришли изображ",
        "отправь изображ",
        "сформируй и отправ",
        "сделай и отправ",
    )
    return any(m in low for m in markers)
