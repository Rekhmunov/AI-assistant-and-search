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
    r"покаж(?:и|ите)\s+(?:мне\s+)?|"
    r"найди\s+(?:мне\s+)?(?:фото|картин(?:ку|ки)|изображени(?:е|я))\s+|"
    r"фото\s+"
    r")",
    re.I,
)

_NO_IMAGE_INTENTS = frozenset({"howto", "edit_prior", "chitchat", "document", "vision_image"})

_NO_IMAGE_TOPIC_TYPES = frozenset({"product_tech", "numeric", "program"})

_SHOW_ENTITY_RE = re.compile(
    r"покаж(?:и|ите)\s+(?:мне\s+)?"
    r"(?!как\b|шаг|пример|код|макрос|функци|формул|sql|excel|эксель)",
    re.I,
)

_DEICTIC_RE = re.compile(
    r"(?:"
    r"\bэт(?:от|ого|ой|ом|а|у|и)\b|"
    r"\bэто\b|"
    r"\bтак(?:ой|ая|ое|ие)\s+(?:бренд|фирм|компани)|"
    r"\b(?:его|её|их)\s+(?:товар|продукт|ассортимент|каталог)|"
    r"\bthis\s+(?:brand|company)\b|"
    r"\bthe\s+brand\b"
    r")",
    re.I,
)

_VAGUE_ENTITY_RE = re.compile(
    r"\b(?:бренд|фирм|компани|товар|продукт|ассортимент|каталог)\b",
    re.I,
)

_NAMED_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,})\b",
)

# Слова из web-search planner — не для Yandex Image Search
_IMAGE_QUERY_NOISE_RE = re.compile(
    r"(?:"
    r"\bapi\b|\bsdk\b|документац|developer|developers|"
    r"инструкц|настройк|webhook|endpoint|"
    r"официальн|котировк|цб\b|usd\b|eur\b|"
    r"telegram\s+bot|kubernetes|docker\b|"
    r"истори(?:я|и)\b|достопримечательност"
    r")",
    re.I,
)


def wants_entity_images(
    query: str,
    *,
    intent: str = "factual_current",
    topic_type: str = "general",
) -> bool:
    q = (query or "").strip()
    if not q or len(q) > 500:
        return False
    if intent in _NO_IMAGE_INTENTS:
        return False
    if topic_type in _NO_IMAGE_TOPIC_TYPES:
        return False
    if _EXCLUDE_IMAGE_RE.search(q):
        return False
    if is_image_display_request(q):
        return True
    if _SHOW_ENTITY_RE.search(q):
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


def _looks_like_named_entity(text: str) -> bool:
    return bool(_NAMED_ENTITY_RE.search(text or ""))


def query_needs_thread_context(user_query: str, local_query: str) -> bool:
    """True, если image query из одного текущего сообщения не содержит конкретной сущности."""
    user = (user_query or "").strip()
    local = (local_query or "").strip()
    if not local:
        return True
    if _DEICTIC_RE.search(user):
        return True
    if _VAGUE_ENTITY_RE.search(local) and not _looks_like_named_entity(local):
        return True
    return False


def _strip_image_query_noise(text: str) -> str:
    cleaned = _IMAGE_QUERY_NOISE_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip(" ,.")


def _is_visual_friendly_rewriter_query(text: str) -> bool:
    q = (text or "").strip()
    if len(q) < 2:
        return False
    if _IMAGE_QUERY_NOISE_RE.search(q):
        return False
    return True


def enrich_visual_image_query(local_query: str, *, topic_type: str = "general") -> str:
    """Добавляет визуальный контекст для Image Search (не web search)."""
    base = _strip_image_query_noise(local_query).strip()
    if not base:
        return base
    lower = base.lower()
    if "фото" in lower or "photo" in lower or "images" in lower:
        return base[:120]
    if topic_type == "place":
        return f"{base} город фото"[:120]
    if topic_type == "general" and len(base.split()) <= 5:
        return f"{base} фото"[:120]
    return base[:120]


def resolve_entity_image_query(
    user_query: str,
    llm_query: str = "",
    *,
    search_queries: list[str] | None = None,
    is_continuation: bool = False,
    topic_type: str = "general",
) -> str:
    """
    Запрос для Yandex Image Search.

    search_queries от Search Planner — для веб-текста, не подставляем их напрямую
    (иначе «Иваново история» или «Bot API docs» дают технические/текстовые картинки).
    Rewriter используем только при местоименной отсылке в треде, если запрос визуальный.
    """
    local = build_entity_image_query(user_query, llm_query)

    if topic_type in _NO_IMAGE_TOPIC_TYPES:
        return enrich_visual_image_query(local, topic_type="general")

    if is_continuation and query_needs_thread_context(user_query, local):
        for candidate in search_queries or []:
            rewritten = (candidate or "").strip()
            if _is_visual_friendly_rewriter_query(rewritten):
                return enrich_visual_image_query(rewritten, topic_type=topic_type)

    return enrich_visual_image_query(local, topic_type=topic_type)
