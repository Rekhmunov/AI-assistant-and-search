"""Единая фабрика тредов — явный thread_type, чтобы не смешивать поиск и агентов."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thread import Thread, ThreadType


async def next_agent_seq(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(Thread.agent_seq), 0)).where(
            Thread.user_id == user_id,
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    current = int(result.scalar_one() or 0)
    return current + 1


async def create_thread(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    thread_type: str = ThreadType.SEARCH,
    agent_seq: int | None = None,
) -> Thread:
    thread = Thread(
        user_id=user_id,
        title=title[:500],
        thread_type=thread_type,
        agent_seq=agent_seq,
    )
    db.add(thread)
    await db.flush()
    return thread
