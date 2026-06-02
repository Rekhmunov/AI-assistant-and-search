"""Запросы на генерацию изображения по тексту (без отдельной кнопки в UI)."""

from __future__ import annotations

import re

# Глагол + опционально «мне/пожалуйста» + объект с картинкой/изображением/иллюстрацией/рисунок/арт
_IMAGE_GEN_RE = re.compile(
    r"(?i)(?:"
    r"нарисуй|нарисовать|рисуй|рисунок|"
    r"сгенерируй|сгенерировать|генерируй|генерация|"
    r"создай|создать|"
    r"сделай|сделать|"
    r"нарисуйте|сгенерируйте|создайте|сделайте"
    r")"
    r"(?:\s+(?:мне|пожалуйста|pls|please))?\s+"
    r"(?:картинк|изображен|иллюстрац|фото|рисун|арт|шедевр|png|логотип)",
)

# Короткие команды: «нарисуй кота», «картинка: закат»
_IMAGE_GEN_SHORT_RE = re.compile(
    r"(?i)^(?:"
    r"(?:нарисуй|сгенерируй|создай|сделай|рисуй)\s+.{3,}"
    r"|(?:картинка|изображение|иллюстрация|арт)\s*[:—-]\s*.+"
    r")$",
)


def wants_image_generation(query: str) -> bool:
    text = (query or "").strip()
    if len(text) < 4:
        return False
    if _IMAGE_GEN_SHORT_RE.match(text):
        return True
    return bool(_IMAGE_GEN_RE.search(text))


def image_generation_prompt(query: str) -> str:
    """Промпт для GigaChat text2image — явная команда «нарисуй»."""
    text = (query or "").strip()
    if re.search(r"(?i)нарисуй|рисуй|сгенерируй|создай|сделай", text):
        return text
    return f"Нарисуй: {text}"
