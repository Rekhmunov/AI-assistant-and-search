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


def enhance_search_query(query: str, *, for_howto: bool | None = None) -> str:
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

    return text[:400]
