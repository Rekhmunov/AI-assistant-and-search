"""Промпты ответов для GigaChat (текст + vision)."""

from __future__ import annotations

from app.services.prompts.yandex_answer_core import (
    ANSWER_DIRECT,
    ANSWER_DOCUMENT,
    ANSWER_META,
    ANSWER_SEARCH,
    ANSWER_VISION,
)

GIGACHAT_ANSWER_SEARCH = ANSWER_SEARCH
GIGACHAT_ANSWER_META = ANSWER_META
GIGACHAT_ANSWER_DIRECT = ANSWER_DIRECT
GIGACHAT_ANSWER_DOCUMENT = ANSWER_DOCUMENT
GIGACHAT_ANSWER_VISION = ANSWER_VISION

GIGACHAT_VISION_SEARCH_SUMMARY = """Ты помощник Glosix. По фото нужно подготовить данные для веб-поиска.

Кратко (до 600 слов), по-русски:
- что на изображении (товар, бренд, модель, текст на упаковке, цифры);
- что именно имеет смысл искать в интернете, чтобы ответить на вопрос пользователя.

Без отказов и без «я не могу». Без markdown-заголовков #. Не выдумывай то, чего не видно."""

GIGACHAT_ANSWER_PROMPT_IDS: dict[str, str] = {
    "gigachat_answer_search": GIGACHAT_ANSWER_SEARCH,
    "gigachat_answer_meta": GIGACHAT_ANSWER_META,
    "gigachat_answer_direct": GIGACHAT_ANSWER_DIRECT,
    "gigachat_answer_document": GIGACHAT_ANSWER_DOCUMENT,
    "gigachat_answer_vision": GIGACHAT_ANSWER_VISION,
}
