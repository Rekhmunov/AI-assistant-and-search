"""Подгрузка текста страниц для обогащения слабых сниппетов Search."""

import logging
import re
from html import unescape

import httpx

from app.services.llm_provider import SearchSource

logger = logging.getLogger(__name__)

_MAX_BYTES = 120_000
_MAX_EXCERPT = 2_500
_TIMEOUT = 10.0

_STRIP_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> str:
    text = _STRIP_TAGS.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


async def fetch_page_excerpt(url: str) -> str:
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "GlosixBot/1.0 (+https://glosix.app)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            raw = response.content[:_MAX_BYTES]
            charset = response.charset_encoding or "utf-8"
            html = raw.decode(charset, errors="replace")
    except Exception:
        logger.debug("Page fetch failed for %s", url, exc_info=True)
        return ""

    text = _html_to_text(html)
    if len(text) > _MAX_EXCERPT:
        return text[:_MAX_EXCERPT] + "…"
    return text


async def enrich_sources_with_pages(
    sources: list[SearchSource],
    *,
    max_pages: int = 2,
) -> list[SearchSource]:
    """Дополняет сниппеты выдержкой с HTML-страницы (как у Perplexity после клика по ссылке)."""
    out: list[SearchSource] = []
    fetched = 0
    for s in sources:
        excerpt = ""
        if fetched < max_pages and s.url:
            excerpt = await fetch_page_excerpt(s.url)
            if excerpt:
                fetched += 1
        snippet = s.snippet or ""
        if excerpt:
            combined = f"{snippet}\n\nВыдержка со страницы:\n{excerpt}"[:3200]
        else:
            combined = snippet
        out.append(
            SearchSource(
                index=s.index,
                url=s.url,
                title=s.title,
                snippet=combined,
                domain=s.domain,
            )
        )
    return out
