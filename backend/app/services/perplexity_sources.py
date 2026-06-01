"""Маппинг citations / search_results Perplexity Sonar → SearchSource Glosix."""

from __future__ import annotations

from urllib.parse import urlparse

from app.services.llm_provider import SearchSource


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def map_perplexity_sources(
    *,
    search_results: list[dict] | None = None,
    citations: list[str] | None = None,
    max_sources: int = 12,
) -> list[SearchSource]:
    """
    search_results — предпочтительно (title, url, snippet, date).
    citations — fallback: только URL без сниппета.
    """
    out: list[SearchSource] = []
    seen: set[str] = set()

    if search_results:
        for item in search_results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url or url.lower() in seen:
                continue
            seen.add(url.lower())
            title = str(item.get("title") or "").strip() or _domain_from_url(url) or url
            snippet = str(item.get("snippet") or "").strip()
            out.append(
                SearchSource(
                    index=len(out) + 1,
                    url=url,
                    title=title[:500],
                    snippet=snippet[:2000],
                    domain=_domain_from_url(url),
                )
            )
            if len(out) >= max_sources:
                return out

    if out:
        return out

    for url in citations or []:
        u = str(url or "").strip()
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        domain = _domain_from_url(u)
        out.append(
            SearchSource(
                index=len(out) + 1,
                url=u,
                title=domain or u,
                snippet="",
                domain=domain,
            )
        )
        if len(out) >= max_sources:
            break

    return out
