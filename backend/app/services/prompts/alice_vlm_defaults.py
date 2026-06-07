"""Промпты vision для Alice AI VLM (Yandex Cloud)."""

from __future__ import annotations

from app.services.prompts.yandex_answer_core import ANSWER_VISION

ALICE_VLM_ANSWER_VISION = ANSWER_VISION

ALICE_VLM_VISION_SEARCH_SUMMARY = """Ты помощник Glosix. По фото нужно подготовить данные для веб-поиска.

Кратко (до 600 слов), по-русски:
- что на изображении (товар, бренд, модель, текст на упаковке, цифры);
- что именно имеет смысл искать в интернете, чтобы ответить на вопрос пользователя.

Без отказов и без «я не могу». Без markdown-заголовков #. Не выдумывай то, чего не видно."""

ALICE_VLM_ANSWER_PROMPT_IDS: dict[str, str] = {
    "alice_vlm_answer_vision": ALICE_VLM_ANSWER_VISION,
}
