"""База знаний агента: загрузка документов и поиск релевантных фрагментов."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.models.agent_knowledge import AgentKnowledgeChunk
from app.models.uploaded_file import UploadedFile
from app.services.upload_storage import load_upload_bytes

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1400
CHUNK_OVERLAP = 120
MAX_CHUNKS_PER_AGENT = 200
MAX_RETRIEVE = 6


def split_knowledge_text(text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_AGENT:
        end = min(len(text), start + chunk_size)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _tokenize(query: str) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9]{3,}", (query or "").lower())
    return set(words)


def _score_chunk(chunk: str, tokens: set[str]) -> int:
    if not tokens:
        return 0
    low = chunk.lower()
    return sum(1 for t in tokens if t in low)


async def ingest_agent_files(
    db: AsyncSession,
    agent: AgentInstance,
    *,
    user_id: UUID,
    file_ids: list[UUID],
) -> int:
    """Парсит документы и сохраняет чанки в agent_knowledge_chunks. Возвращает число чанков."""
    if not file_ids:
        return 0

    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.user_id == user_id,
            UploadedFile.id.in_(file_ids),
        )
    )
    files = list(result.scalars().all())
    if not files:
        return 0

    await db.execute(delete(AgentKnowledgeChunk).where(AgentKnowledgeChunk.agent_id == agent.id))

    total = 0
    cfg = dict(agent.config or {})
    sources: list[str] = []

    for row in files:
        if (row.media_kind or "").lower() == "image":
            continue
        text = (row.extracted_text or "").strip()
        if not text and row.storage_key:
            try:
                data = await load_upload_bytes(row.storage_key)
                from app.services.file_parser import extract_text

                text = extract_text(row.filename, data).strip()
            except Exception as exc:
                logger.warning("Knowledge ingest failed file=%s: %s", row.id, exc)
                continue
        if not text:
            continue

        chunks = split_knowledge_text(text)
        for index, content in enumerate(chunks):
            db.add(
                AgentKnowledgeChunk(
                    agent_id=agent.id,
                    file_id=row.id,
                    chunk_index=index,
                    source_name=row.filename,
                    content=content,
                )
            )
            total += 1
        sources.append(row.filename)

    cfg["knowledge_sources"] = sources
    cfg["knowledge_chunk_count"] = total
    agent.config = cfg
    await db.flush()
    return total


async def retrieve_knowledge_context(
    db: AsyncSession,
    agent: AgentInstance,
    query: str,
    *,
    limit: int = MAX_RETRIEVE,
) -> str:
    result = await db.execute(
        select(AgentKnowledgeChunk)
        .where(AgentKnowledgeChunk.agent_id == agent.id)
        .order_by(AgentKnowledgeChunk.chunk_index.asc())
    )
    chunks = list(result.scalars().all())
    if not chunks:
        return ""

    tokens = _tokenize(query)
    ranked = sorted(chunks, key=lambda c: _score_chunk(c.content, tokens), reverse=True)
    if tokens and ranked[0] and _score_chunk(ranked[0].content, tokens) > 0:
        picked = ranked[:limit]
    else:
        picked = chunks[:limit]

    parts: list[str] = []
    for item in picked:
        parts.append(f"[{item.source_name}]\n{item.content}")
    return "\n\n---\n\n".join(parts)[:8000]
