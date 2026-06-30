"""Утилиты обработки запросов на генерацию изображений."""

from __future__ import annotations

import re

_GEN_VERB_PREFIX_RE = re.compile(
    r"(?i)^(сгенерируй(?:те)?|сгенерировать|генерируй(?:те)?|генерация|"
    r"создай(?:те)?|создать|сделай(?:те)?|сделать|рисуй(?:те)?|рисунок)\b"
)


def image_generation_prompt(query: str) -> str:
    """Промпт для GigaChat text2image — API надёжно срабатывает на «Нарисуй …»."""
    text = (query or "").strip()
    if re.search(r"(?i)\bнарисуй", text):
        return text
    if _GEN_VERB_PREFIX_RE.search(text):
        return _GEN_VERB_PREFIX_RE.sub("Нарисуй", text, count=1)
    return f"Нарисуй: {text}"


