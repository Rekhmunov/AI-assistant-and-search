"""Очистка артефактов в тексте ответа ассистента."""

from __future__ import annotations

import re

# Пустой fenced-блок в конце: ```\n``` (без языка и без тела).
_TRAILING_EMPTY_FENCE_RE = re.compile(r"(?:\r?\n)+```[ \t]*\r?\n```[ \t]*$")


def strip_trailing_empty_code_fences(text: str) -> str:
    """Убирает пустые ``` … ``` в конце (частый артефакт LLM после markdown-документа)."""
    body = text or ""
    if not body:
        return body
    prev = None
    while prev != body:
        prev = body
        body = _TRAILING_EMPTY_FENCE_RE.sub("", body).rstrip()
    return body
