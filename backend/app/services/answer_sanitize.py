"""Очистка артефактов в тексте ответа ассистента."""

from __future__ import annotations

import re

_TRAILING_EMPTY_FENCE_RE = re.compile(r"(?:\r?\n)?```[ \t]*\r?\n```[ \t]*$")
_TRAILING_OPEN_FENCE_RE = re.compile(r"(?:\r?\n)?```[ \t]*$")


def strip_trailing_empty_code_fences(text: str) -> str:
    """Убирает пустые ``` … ``` и одиночный ``` в конце (частый артефакт после markdown-документа)."""
    body = text or ""
    if not body:
        return body
    prev = None
    while prev != body:
        prev = body
        body = _TRAILING_EMPTY_FENCE_RE.sub("", body).rstrip()
        body = _TRAILING_OPEN_FENCE_RE.sub("", body).rstrip()
    return body
