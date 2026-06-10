"""Жизненный цикл агента: отмена при удалении треда и по фразам пользователя."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
from app.models.thread import Thread
from app.services.agent.reminders import cancel_reminders_for_agent


async def get_agent_for_thread(db: AsyncSession, thread_id: UUID) -> AgentInstance | None:
    result = await db.execute(select(AgentInstance).where(AgentInstance.thread_id == thread_id))
    return result.scalar_one_or_none()


async def cancel_agent(db: AsyncSession, agent: AgentInstance, *, reason: str = "cancelled") -> None:
    await cancel_reminders_for_agent(db, agent.id)
    agent.status = AgentStatus.CANCELLED.value
    agent.cancelled_at = datetime.now(timezone.utc)
    cfg = dict(agent.config or {})
    cfg["cancel_reason"] = reason
    agent.config = cfg


async def cancel_agent_for_thread(db: AsyncSession, thread_id: UUID) -> bool:
    agent = await get_agent_for_thread(db, thread_id)
    if not agent or agent.status == AgentStatus.CANCELLED.value:
        return False
    await cancel_agent(db, agent, reason="thread_deleted")
    return True


async def purge_agent_for_thread(db: AsyncSession, thread_id: UUID) -> bool:
    """Удаляет агента и все напоминания (CASCADE) после soft-delete треда."""
    agent = await get_agent_for_thread(db, thread_id)
    if not agent:
        return False
    await cancel_reminders_for_agent(db, agent.id)
    await db.delete(agent)
    await db.flush()
    return True


async def on_thread_soft_deleted(db: AsyncSession, thread: Thread) -> None:
    if thread.thread_type != "agent":
        return
    await purge_agent_for_thread(db, thread.id)
