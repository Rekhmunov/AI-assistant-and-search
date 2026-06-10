"""Журнал событий агента для отладки (24 ч в треде)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentActivityLog, AgentInstance
from app.models.message import Message, MessageRole

logger = logging.getLogger(__name__)

LOG_RETENTION = timedelta(hours=24)
LOG_MESSAGE_MARKER = "▶ Журнал агента"


async def append_agent_activity_log(
    db: AsyncSession,
    agent: AgentInstance,
    event: str,
    *,
    reminder_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    level: str = "info",
) -> AgentActivityLog:
    row = AgentActivityLog(
        agent_id=agent.id,
        thread_id=agent.thread_id,
        reminder_id=reminder_id,
        event=event[:128],
        level=level[:16],
        details=dict(details or {}),
    )
    db.add(row)
    await db.flush()
    await sync_thread_log_message(db, agent)
    return row


async def sync_thread_log_message(db: AsyncSession, agent: AgentInstance) -> Message | None:
    """Одно свёрнутое сообщение в треде с журналом (удаляется при purge)."""
    cutoff = datetime.now(timezone.utc) - LOG_RETENTION
    result = await db.execute(
        select(AgentActivityLog)
        .where(
            AgentActivityLog.agent_id == agent.id,
            AgentActivityLog.created_at >= cutoff,
        )
        .order_by(AgentActivityLog.created_at.desc())
        .limit(50)
    )
    entries = list(result.scalars().all())
    if not entries:
        await _delete_log_message(db, agent.thread_id)
        return None

    lines = [_format_log_line(e) for e in reversed(entries)]
    body = "\n".join(lines)
    header = f"{LOG_MESSAGE_MARKER} ({len(entries)} за 24 ч)"
    content = f"{header}\n{body}"

    msg = await _find_log_message(db, agent.thread_id)
    if msg:
        msg.content = content
        await db.flush()
        return msg

    msg = Message(
        thread_id=agent.thread_id,
        role=MessageRole.ASSISTANT,
        content=content,
        debug_trace={"agent_activity_log": True},
    )
    db.add(msg)
    from app.models.thread import Thread

    thread = await db.get(Thread, agent.thread_id)
    if thread:
        thread.message_count = (thread.message_count or 0) + 1
        thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


def _format_log_line(entry: AgentActivityLog) -> str:
    ts = entry.created_at.astimezone(timezone.utc).strftime("%H:%M:%S")
    detail = ""
    if entry.details:
        err = entry.details.get("error") or entry.details.get("message")
        if err:
            detail = f" — {str(err)[:200]}"
    return f"[{ts}] {entry.event}{detail}"


async def _find_log_message(db: AsyncSession, thread_id: UUID) -> Message | None:
    result = await db.execute(
        select(Message)
        .where(
            Message.thread_id == thread_id,
            Message.role == MessageRole.ASSISTANT,
            Message.content.like(f"{LOG_MESSAGE_MARKER}%"),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _delete_log_message(db: AsyncSession, thread_id: UUID) -> None:
    msg = await _find_log_message(db, thread_id)
    if msg:
        await db.delete(msg)


async def list_agent_activity_logs(
    db: AsyncSession,
    *,
    thread_id: UUID,
    user_id: UUID,
) -> list[AgentActivityLog]:
    cutoff = datetime.now(timezone.utc) - LOG_RETENTION
    result = await db.execute(
        select(AgentActivityLog)
        .join(AgentInstance)
        .where(
            AgentActivityLog.thread_id == thread_id,
            AgentInstance.user_id == user_id,
            AgentActivityLog.created_at >= cutoff,
        )
        .order_by(AgentActivityLog.created_at.desc())
        .limit(200)
    )
    return list(result.scalars().all())


async def purge_old_agent_activity_logs(db: AsyncSession) -> tuple[int, int]:
    """Удаляет записи старше 24 ч и связанные сообщения-журналы в тредах."""
    cutoff = datetime.now(timezone.utc) - LOG_RETENTION
    old_threads = await db.execute(
        select(AgentActivityLog.thread_id)
        .where(AgentActivityLog.created_at < cutoff)
        .distinct()
    )
    thread_ids = [row[0] for row in old_threads.fetchall()]

    result = await db.execute(
        delete(AgentActivityLog).where(AgentActivityLog.created_at < cutoff).returning(AgentActivityLog.id)
    )
    deleted = len(result.scalars().all())

    messages_removed = 0
    for thread_id in thread_ids:
        remaining = await db.execute(
            select(AgentActivityLog.id)
            .where(
                AgentActivityLog.thread_id == thread_id,
                AgentActivityLog.created_at >= cutoff,
            )
            .limit(1)
        )
        if remaining.scalar_one_or_none() is None:
            msg = await _find_log_message(db, thread_id)
            if msg:
                await db.delete(msg)
                messages_removed += 1

    if deleted:
        logger.info("purge_agent_activity_logs: removed %s log rows, %s messages", deleted, messages_removed)
    return deleted, messages_removed
