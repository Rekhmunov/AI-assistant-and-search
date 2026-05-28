"""Маршрутизация vision: только описание фото vs выжимка + веб-поиск."""

from __future__ import annotations

import re

# Явный запрос «опиши картинку» — без интернета.
VISION_ONLY_MARKERS: tuple[str, ...] = (
    "что на фото",
    "что изображено",
    "что на изображении",
    "опиши фото",
    "опиши изображ",
    "опиши картин",
    "переведи надпис",
    "прочитай фото",
    "что здесь изображ",
    "что ты видишь на",
)

# Запрос актуальных данных — vision-выжимка + RAG.
SEARCH_WITH_VISION_MARKERS: tuple[str, ...] = (
    "найди",
    "поищи",
    "найти ",
    "искать ",
    "поиск ",
    "цена",
    "стоимость",
    "сколько стоит",
    "курс",
    "актуальн",
    "новост",
    "где купить",
    "в интернет",
    "в сети",
    "сравни",
    "рейтинг",
    "отзывы",
    "купить",
    "продаж",
    "наличи",
)


def _norm(q: str) -> str:
    return (q or "").strip().lower()


def is_vision_only_user_query(query: str) -> bool:
    q = _norm(query)
    if not q:
        return True
    return any(m in q for m in VISION_ONLY_MARKERS)


def wants_web_search_with_vision(query: str) -> bool:
    """Фото + текст с намерением поиска → выжимка vision, затем RAG."""
    q = _norm(query)
    if not q:
        return False
    if is_vision_only_user_query(query):
        return False
    return any(m in q for m in SEARCH_WITH_VISION_MARKERS)


_IMAGE_DISPLAY_RE = re.compile(
    r"покаж(?:и|ите)\s+(?:мне\s+)?(?:фото|картин|изображ)|"
    r"show\s+me\s+(?:a\s+|the\s+|an\s+)?(?:photo|picture|image)|"
    r"найди\s+(?:мне\s+)?(?:фото|картин|изображ)|"
    r"пришли\s+(?:фото|картин|изображ)|"
    r"скинь\s+(?:фото|картин|изображ)",
    re.I,
)


def is_image_display_request(query: str) -> bool:
    """Запрос «покажи фото X» без вложения — текстовый ответ по теме, не vision."""
    q = _norm(query)
    if not q:
        return False
    if _IMAGE_DISPLAY_RE.search(q):
        return True
    return q.startswith("фото ") and len(q.split()) >= 2
