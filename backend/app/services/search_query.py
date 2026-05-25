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


_WEATHER_MARKERS = (
    "погод",
    "прогноз",
    "температур",
    "осадк",
    "дожд",
    "снег",
    "ветер",
    "градус",
)

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


_WEATHER_EXCLUDE_MARKERS = (
    "прогноз продаж",
    "прогноз рынк",
    "прогноз выруч",
    "прогноз прибыл",
    "экономическ",
    "бизнес",
    "курс на",
    "курс по",
    "похуден",
)


def is_weather_query(query: str) -> bool:
    q = query.lower()
    if is_course_program_query(q):
        return False
    if any(m in q for m in _WEATHER_EXCLUDE_MARKERS):
        return False
    if "прогноз" in q and not any(m in q for m in _WEATHER_MARKERS if m != "прогноз"):
        return False
    return any(m in q for m in _WEATHER_MARKERS)


_META_ASSISTANT_RE = re.compile(
    r"(?:^|[\s,.!?])(?:"
    r"ты\s+умеешь|ты\s+можешь|что\s+ты\s+умеешь|что\s+ты\s+можешь|"
    r"кто\s+ты|что\s+ты\s+такое|что\s+ты\s+за\s+|"
    r"ты\s+программир|ты\s+кодир|ты\s+разработ|"
    r"ты\s+ии|ты\s+бот|ты\s+нейросет|"
    r"can\s+you\s+code|do\s+you\s+program|who\s+are\s+you|what\s+are\s+you"
    r")",
    re.I,
)


def is_meta_assistant_query(query: str) -> bool:
    """Вопросы о возможностях Glosix — без веб-поиска (иначе выдача про «поисковых ассистентов»)."""
    q = query.strip()
    if len(q) > 220:
        return False
    if _has_attachment_marker(q):
        return False
    return bool(_META_ASSISTANT_RE.search(q))


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


def is_course_program_query(query: str) -> bool:
    from app.services.currency_rates import is_course_program_query as _is

    return _is(query)


def is_currency_rate_query(query: str) -> bool:
    from app.services.currency_rates import is_currency_rate_query as _is

    return _is(query)


def build_course_search_queries(user_query: str, llm_queries: list[str]) -> list[str]:
    """Поиск программ/курсов (похудение, обучение), не курс валют."""
    base = (llm_queries[0] if llm_queries else user_query).strip()
    u = user_query.lower()
    b = base.lower()
    parts = [base]
    if "программ" not in b and "план" not in b:
        parts.append("программа")
    if "похуден" in u and "похуден" not in b:
        parts.extend(["похудение", "план питания"])
    primary = " ".join(parts).strip()[:400]
    secondary = f"{primary} этапы рекомендации"[:400]
    return [primary, secondary]


def build_currency_search_queries(user_query: str, llm_queries: list[str]) -> list[str]:
    """Запросы на страницы с котировками, не «где узнать курс»."""
    base = (llm_queries[0] if llm_queries else user_query).strip()
    u = user_query.lower()
    b = base.lower()
    parts = [base]
    if "курс" not in b:
        parts.append("курс")
    if "рубл" not in b and "rub" not in b:
        parts.append("рубль")
    if "сегодня" in u or "сейчас" in u:
        if "сегодня" not in b:
            parts.append("сегодня")
    if "цб" not in b and "cbr" not in b:
        parts.append("ЦБ РФ")
    primary = " ".join(parts).strip()[:400]
    secondary = f"{primary} котировка цифры"[:400]
    if secondary.lower() == primary.lower():
        secondary = f"site:cbr.ru курс доллара рубль сегодня"[:400]
    return [primary, secondary]


def build_weather_search_queries(user_query: str, llm_queries: list[str]) -> list[str]:
    """Запросы на страницы с цифрами прогноза, а не «где посмотреть погоду»."""
    base = (llm_queries[0] if llm_queries else user_query).strip()
    u = user_query.lower()
    b = base.lower()
    parts = [base]
    for token in ("прогноз", "температура"):
        if token not in b:
            parts.append(token)
    for token in ("завтра", "сегодня"):
        if token in u and token not in b:
            parts.append(token)
    if "погод" not in b:
        parts.append("погода")
    primary = " ".join(parts).strip()[:400]
    secondary = f"{primary} градусы осадки ветер"[:400]
    if secondary.lower() == primary.lower():
        secondary = f"{primary} почасовой прогноз"[:400]
    return [primary, secondary]


def enhance_search_query(
    query: str,
    *,
    for_howto: bool | None = None,
    for_weather: bool = False,
    for_currency: bool = False,
) -> str:
    """
    Улучшает запрос для Yandex Search: исправляет опечатки, добавляет контекст для how-to.
    """
    text = normalize_user_query(query)
    howto = for_howto if for_howto is not None else is_howto_query(text)

    if howto and is_yandex_product_query(text):
        # Дублируем ключевые термины для выдачи официальной документации
        extras = []
        if "cloud" not in text.lower() and "облак" not in text.lower():
            extras.append("Yandex Cloud API")
        if "документац" not in text.lower():
            extras.append("официальная документация")
        if extras:
            return f"{text} {' '.join(extras)}"[:400]

    if howto:
        return f"{text} инструкция настройка"[:400]

    if for_weather or is_weather_query(text):
        parts = [text]
        low = text.lower()
        for token in ("прогноз", "температура"):
            if token not in low:
                parts.append(token)
        return " ".join(parts)[:400]

    if is_course_program_query(text):
        low = text.lower()
        parts = [text]
        if "программ" not in low:
            parts.append("программа")
        if "похуден" in low:
            parts.append("похудение план")
        return " ".join(parts)[:400]

    if for_currency or is_currency_rate_query(text):
        low = text.lower()
        parts = [text]
        for token in ("курс", "рубль"):
            if token not in low:
                parts.append(token)
        if "цб" not in low:
            parts.append("ЦБ РФ")
        if "сегодня" not in low:
            parts.append("сегодня")
        return " ".join(parts)[:400]

    return text[:400]
