"""Глубокое чтение страниц: полный текст → чанки → отбор под запрос."""

import logging
import re
from collections.abc import Sequence

from app.services.currency_rates import is_course_program_query
from app.services.llm_provider import SearchSource
from app.services.source_page_fetch import fetch_page_full_text

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 900
_CHUNK_OVERLAP = 120
_MAX_CHUNKS_PER_PAGE = 4
_DEFAULT_MAX_PAGES = 8

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{3,}")

_FINANCIAL_MARKERS = (
    "оборот",
    "выручк",
    "revenue",
    "turnover",
    "прибыл",
    "убыт",
    "ebitda",
    "огрн",
    "бухгалтер",
    "финансов",
    "отчёт",
    "отчет",
)

_INN_RE = re.compile(r"\bинн\s*\d{10}\b", re.I)
_INN_CONTEXT_RE = re.compile(
    r"\bинн\b.{0,40}\b(?:огрн|ооо|ао|компан|организац|юрлиц)",
    re.I,
)

FINANCIAL_NUMBER_RE = re.compile(
    r"\d[\d\s]{0,12}(?:[.,]\d+)?\s*(?:млн|млрд|тыс|₽|руб|%)",
    re.I,
)


def is_financial_query(query: str) -> bool:
    q = query.lower()
    if is_course_program_query(q):
        return False
    if _INN_RE.search(q) or _INN_CONTEXT_RE.search(q):
        return True
    return any(m in q for m in _FINANCIAL_MARKERS)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _score_chunk(chunk: str, query_tokens: set[str], *, financial: bool) -> float:
    low = chunk.lower()
    hits = sum(1 for t in query_tokens if t in low)
    score = hits / max(len(query_tokens), 1)
    if financial and FINANCIAL_NUMBER_RE.search(chunk):
        score += 0.45
    if financial and any(m in low for m in ("2024", "2025", "2023", "оборот", "выручк")):
        score += 0.25
    if len(chunk) < 80:
        score -= 0.2
    return score


def select_relevant_chunks(
    text: str,
    query: str,
    *,
    max_chunks: int = _MAX_CHUNKS_PER_PAGE,
) -> list[str]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        query_tokens = _tokenize(query[:200])
    financial = is_financial_query(query)
    chunks = chunk_text(text)
    if not chunks:
        return []
    scored = [(c, _score_chunk(c, query_tokens, financial=financial)) for c in chunks]
    scored.sort(key=lambda x: -x[1])
    out: list[str] = []
    for c, s in scored:
        if s < 0.08 and out:
            break
        out.append(c)
        if len(out) >= max_chunks:
            break
    if not out and chunks:
        out = chunks[:max_chunks]
    return out


def build_deep_snippet(
    search_snippet: str,
    page_chunks: Sequence[str],
    *,
    max_total: int = 12_000,
) -> str:
    parts = []
    if search_snippet.strip():
        parts.append(f"Сниппет поиска:\n{search_snippet.strip()[:1200]}")
    if page_chunks:
        parts.append("Релевантные фрагменты страницы:")
        for i, ch in enumerate(page_chunks, 1):
            parts.append(f"--- фрагмент {i} ---\n{ch}")
    combined = "\n\n".join(parts)
    if len(combined) > max_total:
        return combined[: max_total - 1] + "…"
    return combined


async def enrich_sources_deep(
    sources: list[SearchSource],
    query: str,
    *,
    max_pages: int = _DEFAULT_MAX_PAGES,
    chunks_per_page: int = _MAX_CHUNKS_PER_PAGE,
) -> tuple[list[SearchSource], dict[str, int]]:
    """Качает полный текст страницы и подставляет лучшие чанки под запрос."""
    out: list[SearchSource] = []
    fetched = 0
    cache_hits = 0
    cache_misses = 0
    for s in sources:
        page_chunks: list[str] = []
        if fetched < max_pages and s.url:
            full, from_cache = await fetch_page_full_text(s.url)
            if from_cache:
                cache_hits += 1
            elif full:
                cache_misses += 1
            if full:
                fetched += 1
                page_chunks = select_relevant_chunks(
                    full, query, max_chunks=chunks_per_page
                )
                logger.debug(
                    "Deep page %s: %d chars → %d chunks (cache=%s)",
                    s.domain,
                    len(full),
                    len(page_chunks),
                    from_cache,
                )
        combined = build_deep_snippet(s.snippet or "", page_chunks)
        out.append(
            SearchSource(
                index=s.index,
                url=s.url,
                title=s.title,
                snippet=combined,
                domain=s.domain,
            )
        )
    stats = {"hits": cache_hits, "misses": cache_misses, "fetched": fetched}
    return out, stats
