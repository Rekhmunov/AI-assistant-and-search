"""Приоритизация источников: официальные домены и релевантность how-to."""

from urllib.parse import urlparse

from app.services.llm_provider import SearchSource

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


def _url_bonus(url: str, title: str, *, howto: bool) -> int:
    combined = f"{url} {title}".lower()
    bonus = 0
    if howto:
        if any(h in combined for h in _HOWTO_URL_HINTS):
            bonus -= 8
        if any(h in combined for h in _LOW_QUALITY_HINTS):
            bonus += 15
    return bonus


def rank_sources(sources: list[SearchSource], *, howto: bool = False) -> list[SearchSource]:
    if not sources:
        return sources

    def sort_key(s: SearchSource) -> tuple[int, int]:
        domain = urlparse(s.url).netloc.replace("www.", "") if s.url else s.domain
        return (_domain_score(domain) + _url_bonus(s.url, s.title, howto=howto), s.index)

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
