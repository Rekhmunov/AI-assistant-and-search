"""Сброс контекста диалога агента по запросу пользователя."""

from __future__ import annotations

import re
from uuid import UUID

from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.services.agent.capabilities import _has_task_hint
from app.services.agent.llm_onboarding import user_wants_cancel

_CONTEXT_RESET_MARKERS = (
    "сбрось контекст",
    "сбросить контекст",
    "очисти контекст",
    "очистить контекст",
    "сброс контекста",
    "сбрось историю",
    "сбросить историю",
    "забудь предыдущ",
    "забудь всё",
    "забудь все",
    "забудь контекст",
    "начни заново",
    "начни сначала",
    "начнём заново",
    "начнем заново",
    "начать заново",
    "новый диалог",
    "очисти историю",
    "очистить историю",
    "reset context",
    "clear context",
)

_PURE_RESET_RE = re.compile(
    r"^[\s,.!?«»\"'`—–-]*(?:"
    + "|".join(re.escape(m) for m in _CONTEXT_RESET_MARKERS)
    + r")[\s,.!?«»\"'`—–-]*$",
    re.I,
)


def user_wants_context_reset(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low or user_wants_cancel(text):
        return False
    return any(marker in low for marker in _CONTEXT_RESET_MARKERS)


def is_pure_context_reset_request(text: str) -> bool:
    """Только сброс без новой задачи в том же сообщении."""
    raw = (text or "").strip()
    if not raw or not user_wants_context_reset(raw):
        return False
    if _PURE_RESET_RE.match(raw):
        return True
    if _has_task_hint(raw):
        return False
    low = raw.lower()
    for marker in _CONTEXT_RESET_MARKERS:
        if marker not in low:
            continue
        remainder = low.replace(marker, " ").strip(" .,!?:;—-")
        if not remainder or len(remainder) < 8:
            return True
    return False


def mark_context_reset(agent: AgentInstance, user_message_id: UUID) -> None:
    cfg = dict(agent.config or {})
    cfg["context_reset_after_message_id"] = str(user_message_id)
    cfg.pop("awaiting_confirmation", None)
    agent.config = cfg


def apply_onboarding_reset(agent: AgentInstance) -> None:
    """Сброс настройки, не останавливая уже активного агента в MAX."""
    cfg = dict(agent.config or {})
    preserve = {
        "knowledge_chunk_count",
        "knowledge_sources",
        "registered_group_chat_id",
        "thread_chat_id",
        "context_reset_after_message_id",
    }
    new_cfg = {k: v for k, v in cfg.items() if k in preserve}
    new_cfg["checklist"] = {}
    new_cfg["awaiting_confirmation"] = False
    agent.config = new_cfg
    agent.role = None
    agent.status = AgentStatus.DRAFT.value


def history_messages_for_agent(messages: list[Message], agent: AgentInstance) -> list[dict[str, str]]:
    sorted_msgs = sorted(messages, key=lambda x: x.created_at)
    cfg = dict(agent.config or {}) if isinstance(agent.config, dict) else {}
    reset_after = cfg.get("context_reset_after_message_id")
    if reset_after:
        trimmed: list[Message] = []
        after_reset = False
        for msg in sorted_msgs:
            if str(msg.id) == str(reset_after):
                after_reset = True
                trimmed = [msg]
                continue
            if after_reset:
                trimmed.append(msg)
        if trimmed:
            sorted_msgs = trimmed

    out: list[dict[str, str]] = []
    for msg in sorted_msgs:
        if msg.role == MessageRole.USER:
            out.append({"role": "user", "text": msg.content})
        elif msg.role == MessageRole.ASSISTANT:
            out.append({"role": "assistant", "text": msg.content})
    return out


def context_reset_reply(agent: AgentInstance) -> str:
    if agent.status == AgentStatus.ACTIVE.value:
        return (
            "Контекст диалога сброшен. Агент в MAX продолжает работать по прежним настройкам.\n\n"
            "Опишите, чем помочь."
        )
    return "Контекст сброшен. Опишите новую задачу для агента — своими словами."
