"""Глубокое чтение страниц: полный текст → чанки → отбор под запрос."""

import asyncio
import logging
import re
from collections.abc import Sequence

from app.core.config import get_settings
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


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    if not text or len(text) <= size:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _score_chunk(chunk: str, query_tokens: set[str], *, financial: bool) -> float:
    chunk_tokens = _tokenize(chunk)
    if not chunk_tokens:
        return 0.0
    overlap = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
    score = overlap
    if financial and FINANCIAL_NUMBER_RE.search(chunk):
        score += 0.35
    return score


def select_relevant_chunks(
    text: str,
    query: str,
    *,
    max_chunks: int = _MAX_CHUNKS_PER_PAGE,
    financial: bool = False,
) -> list[str]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        query_tokens = _tokenize(query[:200])
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


def snippet_is_rich(snippet: str) -> bool:
    """Сниппет Search достаточен — полную страницу можно не качать."""
    settings = get_settings()
    return len((snippet or "").strip()) >= settings.page_fetch_skip_rich_snippet_chars


def _snippet_already_rich(snippet: str) -> bool:
    return snippet_is_rich(snippet)


def effective_page_fetch_limit(
    sources: Sequence[SearchSource],
    *,
    base_max: int,
) -> int:
    """
    Сколько страниц ещё имеет смысл качать: базовый лимит минус источники с богатым сниппетом.
    """
    if base_max <= 0 or not sources:
        return max(0, base_max)
    rich = sum(1 for s in sources if snippet_is_rich(s.snippet or ""))
    return max(0, base_max - rich)


async def _enrich_one_source(
    s: SearchSource,
    query: str,
    *,
    chunks_per_page: int,
    financial: bool,
    sem: asyncio.Semaphore,
    allow_fetch: bool,
) -> tuple[SearchSource, bool, bool, bool]:
    """Возвращает (source, did_fetch, cache_hit, cache_miss)."""
    page_chunks: list[str] = []
    did_fetch = False
    cache_hit = False
    cache_miss = False

    if allow_fetch and s.url and not _snippet_already_rich(s.snippet or ""):
        async with sem:
            full, from_cache = await fetch_page_full_text(s.url)
        if from_cache:
            cache_hit = True
        elif full:
            cache_miss = True
        if full:
            did_fetch = True
            page_chunks = select_relevant_chunks(
                full,
                query,
                max_chunks=chunks_per_page,
                financial=financial,
            )
            logger.debug(
                "Deep page %s: %d chars → %d chunks (cache=%s)",
                s.domain,
                len(full),
                len(page_chunks),
                from_cache,
            )

    combined = build_deep_snippet(s.snippet or "", page_chunks)
    return (
        SearchSource(
            index=s.index,
            url=s.url,
            title=s.title,
            snippet=combined,
            domain=s.domain,
        ),
        did_fetch,
        cache_hit,
        cache_miss,
    )


async def enrich_sources_deep(
    sources: list[SearchSource],
    query: str,
    *,
    max_pages: int = _DEFAULT_MAX_PAGES,
    chunks_per_page: int = _MAX_CHUNKS_PER_PAGE,
    financial: bool = False,
) -> tuple[list[SearchSource], dict[str, int]]:
    """Параллельно качает тексты страниц (с лимитом concurrency) и подставляет чанки."""
    settings = get_settings()
    concurrency = max(1, min(settings.page_fetch_max_concurrent, 8))
    sem = asyncio.Semaphore(concurrency)

    fetch_budget = max_pages
    tasks: list[tuple[int, asyncio.Task]] = []
    for i, s in enumerate(sources):
        allow = fetch_budget > 0 and bool(s.url) and not _snippet_already_rich(s.snippet or "")
        if allow:
            fetch_budget -= 1
        task = asyncio.create_task(
            _enrich_one_source(
                s,
                query,
                chunks_per_page=chunks_per_page,
                financial=financial,
                sem=sem,
                allow_fetch=allow,
            )
        )
        tasks.append((i, task))

    results: list[SearchSource | None] = [None] * len(sources)
    fetched = 0
    cache_hits = 0
    cache_misses = 0

    gathered = await asyncio.gather(*(t for _, t in tasks))
    for (i, _), result in zip(tasks, gathered):
        src, did_fetch, hit, miss = result
        results[i] = src
        if did_fetch:
            fetched += 1
        if hit:
            cache_hits += 1
        if miss:
            cache_misses += 1

    out = [r for r in results if r is not None]
    stats = {"hits": cache_hits, "misses": cache_misses, "fetched": fetched}
    return out, stats
