"""Фильтрация служебных инструкций из ответов LLM пользователю."""

from __future__ import annotations

import re

# Только действительно служебные строки — когда LLM "утёк" в мета-режим
_META_MARKERS = (
    "пользователь спрашивает",
    "пользователь просит",
    "пример ответа",
    "черновик ответа",
    "revised_reply",
    "agent_spec:",
    "checklist:",
)

# Только явный системный мусор (JSON-структуры из промпта)
_META_PATTERNS = (
    re.compile(r'"ok"\s*:\s*(true|false)', re.I),
    re.compile(r'"tool_calls"\s*:\s*\[', re.I),
    re.compile(r'"checklist"\s*:\s*\{', re.I),
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
    """Возвращает пустую строку только если ответ — явная служебная структура JSON."""
    text = (reply or "").strip()
    if not text:
        return ""
    if reply_looks_like_meta_instruction(text):
        return ""
    return text
