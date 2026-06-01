"""Нормализация запроса и улучшение поисковой формулировки для веб-поиска."""

import re

# Опечатки и варианты написания
_TYPO_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bGTP\b", re.I), "GPT"),
    (re.compile(r"\bЯндекс\s*GTP\b", re.I), "Yandex GPT"),
    (re.compile(r"\bYandex\s*GTP\b", re.I), "Yandex GPT"),
]

_HOWTO_MARKERS = (
    "распиш",
    "составь",
    "опиши",
    "расскажи подроб",
    "курс на",
    "курс по",
    "как настроить",
    "как подключить",
    "как использовать",
    "как создать",
    "как установить",
    "настройка",
    "настроить",
    "подключить",
    "инструкция",
    "пошагово",
    "пошаговая",
    "setup",
    "configure",
    "getting started",
    "quickstart",
    "быстрый старт",
)

_YANDEX_PRODUCT_MARKERS = (
    "yandex gpt",
    "yandexgpt",
    "яндекс gpt",
    "яндекс gpt",
    "foundation models",
    "yandex cloud",
    "яндекс облако",
)


def normalize_user_query(query: str) -> str:
    text = query.strip()
    for pattern, repl in _TYPO_FIXES:
        text = pattern.sub(repl, text)
    return text


def is_howto_query(query: str) -> bool:
    q = query.lower()
    return any(m in q for m in _HOWTO_MARKERS)


def is_yandex_product_query(query: str) -> bool:
    q = query.lower()
    return any(m in q for m in _YANDEX_PRODUCT_MARKERS)


_PLACE_HINTS = (
    "москв",
    "петербург",
    "спб",
    "санкт-петербург",
    "екатеринбург",
    "новосибирск",
    "казань",
    "нижний",
    "самар",
    "краснодар",
    "сочи",
    "воронеж",
    "ростов",
    "уф",
    "красноярск",
    "перм",
    "волгоград",
    "минск",
    "киев",
    "астан",
    "алмат",
)

_PLACE_IN_RE = re.compile(
    r"\b(?:в|во|на)\s+([а-яё][а-яё\-]{2,}(?:\s+[а-яё][а-яё\-]{2,})?)",
    re.I,
)


_META_ASSISTANT_RE = re.compile(
    r"(?:^|[\s,.!?])(?:"
    r"ты\s+умеешь|ты\s+можешь|что\s+ты\s+умеешь|что\s+ты\s+можешь|"
    r"что\s+ты\s+умеешь\s+делать|чем\s+ты\s+можешь|чем\s+можешь\s+помочь|"
    r"чем\s+поможешь|что\s+умеешь|какие\s+у\s+тебя\s+возможности|"
    r"как\s+ты\s+работаешь|расскажи\s+о\s+себе|"
    r"кто\s+ты|что\s+ты\s+такое|что\s+ты\s+за\s+|"
    r"ты\s+программир|ты\s+кодир|ты\s+разработ|"
    r"ты\s+ии|ты\s+бот|ты\s+нейросет|"
    r"can\s+you\s+code|do\s+you\s+program|who\s+are\s+you|what\s+are\s+you|"
    r"what\s+can\s+you\s+do"
    r")",
    re.I,
)

_CHITCHAT_MAX_LEN = 40

CHITCHAT_EXACT = frozenset(
    {
        "привет",
        "приветик",
        "здравствуй",
        "здравствуйте",
        "hi",
        "hello",
        "hey",
        "хай",
        "спасибо",
        "благодарю",
        "thanks",
        "thank you",
        "thx",
        "ок",
        "окей",
        "okay",
        "как дела",
        "как ты",
        "что нового",
        "че как",
        "чё как",
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "доброй ночи",
        "доброго дня",
        "пока",
        "до свидания",
        "bye",
        "goodbye",
        "good morning",
    }
)

_CHITCHAT_RE = re.compile(
    r"^(?:"
    r"как\s+(?:у\s+тебя\s+|тебя\s+)?дела|"
    r"как\s+ты\s+себя\s+чувствуешь|"
    r"что\s+(?:нового|случилось)"
    r")\??$",
    re.I,
)


def is_chitchat_query(query: str) -> bool:
    """Короткая болтовня — без веб-поиска (ответ только LLM)."""
    stripped = query.strip().lower().rstrip("!?.")
    if not stripped or len(stripped) > _CHITCHAT_MAX_LEN:
        return False
    if stripped in CHITCHAT_EXACT:
        return True
    return bool(_CHITCHAT_RE.match(stripped))


def is_meta_assistant_query(query: str) -> bool:
    """Вопросы о возможностях Glosix — без веб-поиска (иначе выдача про «поисковых ассистентов»)."""
    q = query.strip()
    if len(q) > 220:
        return False
    if _has_attachment_marker(q):
        return False
    if is_chitchat_query(q):
        return False
    return bool(_META_ASSISTANT_RE.search(q))


_VISION_CAPABILITY_RE = re.compile(
    r"(?:"
    r"по\s+(?:фото|изображен|картин)|"
    r"на\s+(?:фото|изображен|картин)|"
    r"калори(?:и|й|ю|я)?.*(?:фото|изображ|картин)|"
    r"(?:фото|изображ|картин).*(?:калори|состав)|"
    r"(?:сч(?:ит|ита)(?:ать|аешь|ает)?|определи|распозна).*"
    r"(?:фото|изображ|картин)|"
    r"(?:фото|изображ|картин).*(?:анализ|распозна|опиши)|"
    r"умеешь.*(?:фото|изображ|картин)|"
    r"можешь.*(?:фото|изображ|картин)"
    r")",
    re.I,
)


def is_vision_capability_question(query: str) -> bool:
    """«Можешь по фото?» без вложения — direct/meta, не vision API."""
    q = query.strip()
    if not q or len(q) > 280:
        return False
    if _has_attachment_marker(q):
        return False
    return bool(_VISION_CAPABILITY_RE.search(q))


def _has_attachment_marker(query: str) -> bool:
    return "--- Документ:" in query or "[Файлы:" in query


def _text_has_place(text: str) -> bool:
    q = text.lower()
    if any(h in q for h in _PLACE_HINTS):
        return True
    return bool(_PLACE_IN_RE.search(q))


def query_has_place(query: str, history: list[tuple[str, str]] | None = None) -> bool:
    if _text_has_place(query):
        return True
    if history:
        for role, text in reversed(history):
            if role == "user" and _text_has_place(text):
                return True
    return False


def enhance_search_query(
    query: str,
    *,
    for_howto: bool | None = None,
    prefer_official_docs: bool = False,
) -> str:
    """
    Улучшает запрос для Yandex Search: исправляет опечатки, добавляет контекст для how-to.
    """
    text = normalize_user_query(query)
    howto = for_howto if for_howto is not None else is_howto_query(text)
    lower = text.lower()

    if howto and is_yandex_product_query(text):
        extras = []
        if "cloud" not in lower and "облак" not in lower:
            extras.append("Yandex Cloud API")
        if "документац" not in lower:
            extras.append("официальная документация")
        if extras:
            return f"{text} {' '.join(extras)}"[:400]

    if howto:
        base = f"{text} инструкция настройка"
        if prefer_official_docs and "документац" not in lower:
            base = f"{base} официальная документация"
        return base[:400]

    return text[:400]


def should_prefer_official_docs(
    *,
    user_query: str,
    search_queries: list[str] | None = None,
    intent: str = "",
) -> bool:
    """Официальная документация — только для IT/продуктов, не для городов и общих тем."""
    if intent == "howto":
        return True
    blob = " ".join([user_query, *(search_queries or [])]).lower()
    markers = (
        " api",
        "api ",
        "sdk",
        "документац",
        "developer",
        "интеграц",
        "webhook",
        "oauth",
        "graphql",
        "endpoint",
        "мини-прилож",
        "мини прилож",
        "платформ",
        "telegram",
        "whatsapp",
        "vk ",
        "бот ",
        " bot",
        "мессенджер",
        "yandex cloud",
        "яндекс облако",
    )
    return any(m in blob for m in markers)
