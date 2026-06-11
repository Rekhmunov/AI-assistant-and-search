"""Убираем из ответа пользователю служебный текст (рефлексия, промпты, meta)."""

from __future__ import annotations

import re

_META_MARKERS = (
    "пользователь спрашивает",
    "пользователь просит",
    "вам нужно",
    "вам следует",
    "пример ответа",
    "не переходите",
    "не начинайте настройку",
    "черновик ответа",
    "revised_reply",
    "tool_calls",
    "ok=false",
    "ok=true",
    "agent_spec:",
    "checklist:",
)

_META_PATTERNS = (
    re.compile(r"каким\s+инструментом", re.I),
    re.compile(r"через\s+инструмент\s+max", re.I),
    re.compile(r"max[_\s]?probe[_\s]?chat", re.I),
    re.compile(r"max[_\s]?send[_\s]?message", re.I),
    re.compile(r"сейчас\s+выполню\s*[—-]\s*ожидайте", re.I),
    re.compile(r"^я\s+проверю\b.*\bотправ", re.I | re.S),
)


def reply_looks_like_meta_instruction(reply: str) -> bool:
    text = (reply or "").strip()
    if len(text) < 12:
        return False
    low = text.lower()
    if any(marker in low for marker in _META_MARKERS):
        return True
    return any(pattern.search(text) for pattern in _META_PATTERNS)


def sanitize_user_facing_reply(reply: str) -> str:
    """Возвращает пустую строку, если ответ — служебная инструкция, а не текст для пользователя."""
    text = (reply or "").strip()
    if not text:
        return ""
    if reply_looks_like_meta_instruction(text):
        return ""
    return text
