"""Объединение результатов нескольких поисковых запросов."""

from urllib.parse import urlparse

from app.services.llm_provider import SearchSource
from app.services.source_ranking import (
    _DOMAIN_PRIORITY,
    _HOWTO_URL_HINTS,
    _OFFICIAL_DOCS_HINTS,
)

DEFAULT_MAX_PER_DOMAIN = 2
OFFICIAL_MAX_PER_DOMAIN = 4
HOWTO_DOC_MAX_PER_DOMAIN = 3


def normalize_source_domain(source: SearchSource) -> str:
    if source.domain:
        return source.domain.lower().replace("www.", "")
    if source.url:
        return urlparse(source.url).netloc.lower().replace("www.", "")
    return ""


def is_official_domain(domain: str) -> bool:
    d = domain.lower().replace("www.", "")
    if not d:
        return False
    for key in _DOMAIN_PRIORITY:
        if d == key or d.endswith("." + key):
            return True
    return d.startswith("developer.") or d.startswith("developers.")


def _domain_cap(
    domain: str,
    url: str,
    title: str,
    *,
    howto: bool,
    prefer_official_docs: bool,
    max_per_domain: int,
    max_per_domain_official: int,
    max_per_domain_howto_doc: int,
) -> int:
    caps = [max_per_domain]
    if is_official_domain(domain):
        caps.append(max_per_domain_official)
    if howto or prefer_official_docs:
        blob = f"{url} {title}".lower()
        if any(h in blob for h in _OFFICIAL_DOCS_HINTS) or any(h in blob for h in _HOWTO_URL_HINTS):
            caps.append(max_per_domain_howto_doc)
    return max(caps)


def diversify_sources_by_domain(
    sources: list[SearchSource],
    *,
    howto: bool = False,
    prefer_official_docs: bool = False,
    max_per_domain: int = DEFAULT_MAX_PER_DOMAIN,
    max_per_domain_official: int = OFFICIAL_MAX_PER_DOMAIN,
    max_per_domain_howto_doc: int = HOWTO_DOC_MAX_PER_DOMAIN,
    max_sources: int | None = None,
) -> list[SearchSource]:
    """Ограничивает число источников с одного домена, сохраняя порядок ранжирования."""
    if not sources:
        return sources

    domain_counts: dict[str, int] = {}
    out: list[SearchSource] = []

    for source in sources:
        domain = normalize_source_domain(source)
        cap = _domain_cap(
            domain,
            source.url,
            source.title,
            howto=howto,
            prefer_official_docs=prefer_official_docs,
            max_per_domain=max_per_domain,
            max_per_domain_official=max_per_domain_official,
            max_per_domain_howto_doc=max_per_domain_howto_doc,
        )
        count = domain_counts.get(domain, 0)
        if count >= cap:
            continue
        domain_counts[domain] = count + 1
        out.append(source)
        if max_sources is not None and len(out) >= max_sources:
            break

    return [
        SearchSource(
            index=i,
            url=s.url,
            title=s.title,
            snippet=s.snippet,
            domain=s.domain,
        )
        for i, s in enumerate(out, start=1)
    ]


def merge_search_sources(
    batches: list[list[SearchSource]],
    *,
    max_sources: int = 12,
    howto: bool = False,
    prefer_official_docs: bool = False,
    max_per_domain: int = DEFAULT_MAX_PER_DOMAIN,
    max_per_domain_official: int = OFFICIAL_MAX_PER_DOMAIN,
    max_per_domain_howto_doc: int = HOWTO_DOC_MAX_PER_DOMAIN,
) -> list[SearchSource]:
    seen: set[str] = set()
    merged: list[SearchSource] = []
    for batch in batches:
        for s in batch:
            key = (s.url or "").strip().lower() or f"title:{s.title}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(s)

    return diversify_sources_by_domain(
        merged,
        howto=howto,
        prefer_official_docs=prefer_official_docs,
        max_per_domain=max_per_domain,
        max_per_domain_official=max_per_domain_official,
        max_per_domain_howto_doc=max_per_domain_howto_doc,
        max_sources=max_sources,
    )
