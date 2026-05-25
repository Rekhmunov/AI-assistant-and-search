"""Уровень 2: память query → URL в Postgres (без краулера)."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.query_url_log import QueryUrlLog
from app.services.llm_provider import SearchSource
from app.services.page_cache import should_cache_url
from app.services.search_query import normalize_user_query

logger = logging.getLogger(__name__)

_DOC_BLOCK_RE = re.compile(r"\n---\s*документ:", re.I)

_table_ok: bool | None = None


@dataclass(frozen=True)
class QueryIndexKey:
    key: str
    normalized: str


@dataclass
class QueryUrlMemoryTrace:
    bootstrap_count: int = 0
    recorded_count: int = 0
    lookup_keys: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "bootstrap": self.bootstrap_count,
            "recorded": self.recorded_count,
            "lookup_keys": self.lookup_keys,
        }


def normalize_query_index(query: str) -> QueryIndexKey:
    text = normalize_user_query(query)
    text = _DOC_BLOCK_RE.split(text)[0].strip().lower()
    text = re.sub(r"\s+", " ", text)
    normalized = text[:480]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return QueryIndexKey(key=digest, normalized=normalized)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:40]


def should_remember_url(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    return should_cache_url(url)


async def _ensure_table(db: AsyncSession) -> bool:
    global _table_ok
    if _table_ok is not None:
        return _table_ok
    try:
        await db.execute(text("SELECT 1 FROM query_url_log LIMIT 0"))
        _table_ok = True
    except ProgrammingError:
        _table_ok = False
        logger.warning("Table query_url_log missing — run alembic upgrade head")
    return _table_ok


async def lookup_bootstrap_sources(
    db: AsyncSession,
    *queries: str,
) -> tuple[list[SearchSource], QueryUrlMemoryTrace]:
    """URL из памяти для подмешивания перед Yandex Search."""
    settings = get_settings()
    trace = QueryUrlMemoryTrace()
    if not settings.query_url_index_enabled:
        return [], trace

    if not await _ensure_table(db):
        return [], trace

    keys: list[QueryIndexKey] = []
    seen_keys: set[str] = set()
    for q in queries:
        if not q or not q.strip():
            continue
        idx = normalize_query_index(q)
        if idx.key in seen_keys:
            continue
        seen_keys.add(idx.key)
        keys.append(idx)
        if len(keys) >= settings.query_url_lookup_keys:
            break
    trace.lookup_keys = len(keys)
    if not keys:
        return [], trace

    max_urls = settings.query_url_max_bootstrap
    seen_url: set[str] = set()
    rows: list[QueryUrlLog] = []

    for idx in keys:
        result = await db.execute(
            select(QueryUrlLog)
            .where(QueryUrlLog.query_key == idx.key)
            .order_by(QueryUrlLog.score.desc(), QueryUrlLog.hit_count.desc())
            .limit(max_urls)
        )
        for row in result.scalars().all():
            u = (row.url or "").strip().lower()
            if not u or u in seen_url:
                continue
            seen_url.add(u)
            rows.append(row)
            if len(rows) >= max_urls:
                break
        if len(rows) >= max_urls:
            break

    if not rows:
        return [], trace

    now = datetime.now(timezone.utc)
    for row in rows:
        row.hit_count = (row.hit_count or 0) + 1
        row.last_used_at = now

    sources = _rows_to_sources(rows)
    trace.bootstrap_count = len(sources)
    return sources, trace


def _rows_to_sources(rows: list[QueryUrlLog]) -> list[SearchSource]:
    out: list[SearchSource] = []
    for i, row in enumerate(rows, start=1):
        url = row.url.strip()
        domain = urlparse(url).netloc.replace("www.", "") if url else ""
        out.append(
            SearchSource(
                index=i,
                url=url,
                title=domain or "источник",
                snippet="Ранее этот URL использовался для ответа на похожий запрос.",
                domain=domain or "unknown",
            )
        )
    return out


async def record_successful_urls(
    db: AsyncSession,
    query: str,
    sources: list[SearchSource],
    *,
    retrieval_score: float,
) -> int:
    """Сохранить топ URL после удачного ответа."""
    settings = get_settings()
    if not settings.query_url_index_enabled or not sources:
        return 0
    if not await _ensure_table(db):
        return 0

    idx = normalize_query_index(query)
    score_base = max(0.05, min(1.0, float(retrieval_score)))
    max_record = settings.query_url_max_record
    recorded = 0
    now = datetime.now(timezone.utc)

    for pos, src in enumerate(sources[:max_record]):
        url = (src.url or "").strip()
        if not should_remember_url(url):
            continue
        u_hash = url_hash(url)
        pos_score = score_base * (1.0 - 0.08 * pos)
        ins = insert(QueryUrlLog).values(
            query_key=idx.key,
            normalized_query=idx.normalized[:512],
            url_hash=u_hash,
            url=url[:2048],
            score=pos_score,
            hit_count=1,
            last_used_at=now,
        )
        ins = ins.on_conflict_do_update(
            constraint="uq_query_url_log_key_url",
            set_={
                "score": func.greatest(QueryUrlLog.score, ins.excluded.score),
                "hit_count": QueryUrlLog.hit_count + 1,
                "last_used_at": now,
                "normalized_query": idx.normalized[:512],
            },
        )
        await db.execute(ins)
        recorded += 1

    if recorded:
        await _prune_query_key(db, idx.key, settings.query_url_max_per_query)
    return recorded


async def _prune_query_key(db: AsyncSession, query_key: str, keep: int) -> None:
    subq = (
        select(QueryUrlLog.id)
        .where(QueryUrlLog.query_key == query_key)
        .order_by(QueryUrlLog.score.desc(), QueryUrlLog.hit_count.desc(), QueryUrlLog.last_used_at.desc())
        .offset(keep)
    )
    await db.execute(delete(QueryUrlLog).where(QueryUrlLog.id.in_(subq)))


async def index_stats(db: AsyncSession) -> dict[str, int | bool]:
    settings = get_settings()
    if not settings.query_url_index_enabled:
        return {"enabled": False, "rows": 0}
    if not await _ensure_table(db):
        return {"enabled": True, "table_ready": False, "rows": 0}
    result = await db.execute(select(func.count()).select_from(QueryUrlLog))
    rows = int(result.scalar() or 0)
    return {"enabled": True, "table_ready": True, "rows": rows}
