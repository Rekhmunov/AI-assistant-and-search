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


_HQ_RE = re.compile(
    r"(?i)"
    r"2[kк]\b|"
    r"высок[оое][\s-]*качеств|"
    r"лучш[еея][\s-]*качеств|"
    r"максимальн[оое][\s-]*качеств|"
    r"hd\b|hq\b|high[\s-]*quality|"
    r"высо[кч][оа][еёй]?\s+разрешени|"
    r"большо[ей]\s+разрешени|"
    r"4[kк]\b"
)


def wants_high_quality(query: str) -> bool:
    """True если пользователь явно просит 2K / высокое качество / высокое разрешение."""
    return bool(_HQ_RE.search((query or "").strip()))
