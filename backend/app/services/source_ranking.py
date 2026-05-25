"""Приоритизация источников: официальные домены и релевантность how-to / погода."""

import re
from urllib.parse import urlparse

from app.services.llm_provider import SearchSource

_WEATHER_DATA_RE = re.compile(
    r"(-?\d{1,2})\s*°|"
    r"(-?\d{1,2})\s*град|"
    r"температур[аы]?\s*(-?\d{1,2})|"
    r"осадк|"
    r"ветер\s+\d|"
    r"облачност",
    re.I,
)

_WEATHER_META_HINTS = (
    "перейдите на сайт",
    "воспользуйтесь сервисом",
    "узнайте на",
    "где посмотреть",
    "список сайтов",
)

# Чем меньше score — тем выше в списке после сортировки
_DOMAIN_PRIORITY: dict[str, int] = {
    "yandex.cloud": 0,
    "cloud.yandex.ru": 1,
    "yandex.ru": 2,
    "ya.ru": 3,
    "education.yandex.ru": 4,
    "yandex.com": 5,
}

_HOWTO_URL_HINTS = (
    "quickstart",
    "docs",
    "documentation",
    "guide",
    "tutorial",
    "настрой",
    "инструк",
    "api",
    "foundation-models",
    "yandexgpt",
)

_LOW_QUALITY_HINTS = (
    "plugin",
    "плагин",
    "объявлен",
    "wordpress",
    "joomla",
)


def _domain_score(domain: str) -> int:
    d = domain.lower().replace("www.", "")
    for key, score in _DOMAIN_PRIORITY.items():
        if d == key or d.endswith("." + key):
            return score
    return 50


def _url_bonus(url: str, title: str, *, howto: bool, weather: bool) -> int:
    combined = f"{url} {title}".lower()
    bonus = 0
    if howto:
        if any(h in combined for h in _HOWTO_URL_HINTS):
            bonus -= 8
        if any(h in combined for h in _LOW_QUALITY_HINTS):
            bonus += 15
    if weather:
        blob = f"{url} {title} {combined}"
        snippet_like = combined
        if _WEATHER_DATA_RE.search(snippet_like):
            bonus -= 25
        if any(h in blob for h in _WEATHER_META_HINTS):
            bonus += 20
        for dom in ("gismeteo", "yandex.ru/pogoda", "weather.com", "meteoinfo", "rp5.ru"):
            if dom in blob:
                bonus -= 5
    return bonus


def _weather_snippet_bonus(snippet: str) -> int:
    if not snippet:
        return 10
    if _WEATHER_DATA_RE.search(snippet):
        return -30
    if any(h in snippet.lower() for h in _WEATHER_META_HINTS):
        return 15
    return 0


def rank_sources(
    sources: list[SearchSource],
    *,
    howto: bool = False,
    weather: bool = False,
) -> list[SearchSource]:
    if not sources:
        return sources

    def sort_key(s: SearchSource) -> tuple[int, int]:
        domain = urlparse(s.url).netloc.replace("www.", "") if s.url else s.domain
        base = _domain_score(domain) + _url_bonus(s.url, s.title, howto=howto, weather=weather)
        if weather:
            base += _weather_snippet_bonus(s.snippet or "")
        return (base, s.index)

    ordered = sorted(sources, key=sort_key)
    return [
        SearchSource(
            index=i,
            url=s.url,
            title=s.title,
            snippet=s.snippet,
            domain=s.domain,
        )
        for i, s in enumerate(ordered, start=1)
    ]
