"""Вспомогательные функции операционного контекста агента."""

from __future__ import annotations

import re

from app.models.agent import AgentInstance
from app.services.agent.intent_hints import _extract_max_chat_id


def user_wants_admin_check(text: str) -> bool:
    low = (text or "").lower()
    if not re.search(r"админ|администратор|admin", low):
        return False
    if _has_write_to_group_intent(low):
        return False
    return True


def is_bare_max_link_message(text: str) -> bool:
    """Сообщение содержит только ссылку/ID группы MAX без другого контента."""
    clean = (text or "").strip()
    if not clean:
        return False
    cid = _extract_max_chat_id(clean)
    if cid is None:
        return False
    noise = {"max", "ru", "web", "http", "https", "группа", "чат", "канал", "ссылка"}
    remainder = clean.lower()
    remainder = re.sub(r"https?://\S+", "", remainder)
    remainder = re.sub(r"-?\d{5,}", "", remainder)
    for token in noise:
        remainder = remainder.replace(token, "")
    remainder = re.sub(r"[^a-zа-яё]", " ", remainder).strip()
    return len(remainder) < 12


def _has_write_to_group_intent(low: str) -> bool:
    return any(
        p in low
        for p in (
            "напиши",
            "отправ",
            "опубликуй",
            "публикуй",
            "прямо сейчас",
            "сейчас напиши",
        )
    )


def is_assist_turn(text: str) -> bool:
    """Запрос на проверку/диагностику, а не настройку автоматизации."""
    clean = (text or "").strip()
    if not clean:
        return False
    if is_operational_max_query(clean):
        return True
    if is_bare_max_link_message(clean):
        return True
    return False


def is_operational_max_query(text: str) -> bool:
    """Диагностический запрос: проверка прав/доступа бота."""
    low = (text or "").lower()
    if _has_write_to_group_intent(low):
        return False
    if user_wants_admin_check(text):
        return True
    cid = _extract_max_chat_id(text)
    probe_phrases = ("провер", "доступ", "бот там", "бот в", "добавлен ли")
    if cid and any(p in low for p in probe_phrases):
        return True
    return False


def bind_chat_to_current_agent(agent: AgentInstance, chat_id: int) -> None:
    """Привязка chat_id только к агенту этого треда."""
    cid = int(chat_id)
    agent.max_chat_id = cid
    cfg = dict(agent.config or {})
    cfg["max_chat_id"] = cid
    cfg["thread_chat_id"] = cid
    agent.config = cfg
