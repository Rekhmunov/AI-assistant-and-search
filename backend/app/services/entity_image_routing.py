"""Когда показывать галерею картинок сущности (не vision-вложение)."""

from __future__ import annotations

import re

from app.services.vision_routing import is_image_display_request

_ENTITY_IMAGE_POSITIVE_RE = re.compile(
    r"(?:"
    r"расскаж\w*\s+(?:про|о\b|об\b)|"
    r"что\s+такое|кто\s+так(?:ой|ая|ие)|"
    r"опиши\s+(?:город|страну|место|животн|породу|архитектур|достоприм)|"
    r"обзор\s+(?:города|страны|породы|места)|"
    r"истор(?:ия|ии)\s+(?:города|страны|породы|места)"
    r")",
    re.I,
)

_EXCLUDE_IMAGE_RE = re.compile(
    r"(?:"
    r"напиш(?:и|ите)|сгенериру(?:й|йте)|состав(?:ь|ьте)|"
    r"макрос|excel|эксель|google\s*sheets|"
    r"код|скрипт|функци|программ|алгоритм|"
    r"курс|погод|сколько\s+стоит|цена\s|"
    r"how\s+to|tutorial|debug|regex|sql|docker|kubernetes"
    r")",
    re.I,
)

_IMAGE_QUERY_PREFIX_RE = re.compile(
    r"^(?:"
    r"расскаж\w*\s+(?:про|о|об)\s+|"
    r"что\s+такое\s+|"
    r"кто\s+так(?:ой|ая|ие)\s+|"
    r"опиши\s+|"
    r"обзор\s+|"
    r"покаж(?:и|ите)\s+(?:мне\s+)?(?:фото|картин(?:ку|ки)|изображени(?:е|я))\s+|"
    r"найди\s+(?:мне\s+)?(?:фото|картин(?:ку|ки)|изображени(?:е|я))\s+|"
    r"фото\s+"
    r")",
    re.I,
)

_NO_IMAGE_INTENTS = frozenset({"howto", "edit_prior", "chitchat", "document", "vision_image"})


def wants_entity_images(query: str, *, intent: str = "factual_current") -> bool:
    q = (query or "").strip()
    if not q or len(q) > 500:
        return False
    if intent in _NO_IMAGE_INTENTS:
        return False
    if _EXCLUDE_IMAGE_RE.search(q):
        return False
    if is_image_display_request(q):
        return True
    return bool(_ENTITY_IMAGE_POSITIVE_RE.search(q))


def build_entity_image_query(user_query: str, llm_query: str = "") -> str:
    q = (user_query or "").strip()
    if not q:
        return (llm_query or "")[:120]
    stripped = _IMAGE_QUERY_PREFIX_RE.sub("", q, count=1).strip(" ?!.,")
    if len(stripped) >= 2:
        return stripped[:120]
    fallback = (llm_query or q).strip()
    return fallback[:120] if fallback else q[:120]
