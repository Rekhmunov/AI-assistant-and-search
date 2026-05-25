"""Нормализация запроса и улучшение поисковой формулировки для веб-поиска."""

import re

# Опечатки и варианты написания
_TYPO_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bGTP\b", re.I), "GPT"),
    (re.compile(r"\bЯндекс\s*GTP\b", re.I), "Yandex GPT"),
    (re.compile(r"\bYandex\s*GTP\b", re.I), "Yandex GPT"),
]

_HOWTO_MARKERS = (
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


def is_weather_query(query: str) -> bool:
    q = query.lower()
    return any(m in q for m in _WEATHER_MARKERS)


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

    return text[:400]
