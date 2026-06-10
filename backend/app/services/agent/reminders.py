"""Создание и отмена напоминаний агента."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.onboarding import validate_activation
from app.services.agent.schedule import parse_reminder_schedule


async def cancel_reminders_for_agent(db: AsyncSession, agent_id: UUID) -> int:
    result = await db.execute(
        update(AgentReminder)
        .where(AgentReminder.agent_id == agent_id, AgentReminder.status == "pending")
        .values(status="cancelled")
        .returning(AgentReminder.id)
    )
    return len(result.scalars().all())


async def activate_agent_reminders(db: AsyncSession, agent: AgentInstance) -> AgentReminder:
    validate_activation(agent)
    await cancel_reminders_for_agent(db, agent.id)

    cfg = dict(agent.config or {})
    run_at, recurrence = parse_reminder_schedule(str(cfg["schedule_text"]))
    reminder = AgentReminder(
        agent_id=agent.id,
        run_at=run_at,
        message_text=str(cfg["reminder_message"]),
        recurrence=recurrence,
        status="pending",
    )
    db.add(reminder)
    agent.status = AgentStatus.ACTIVE.value
    await db.flush()
    return reminder


async def schedule_next_recurrence(db: AsyncSession, reminder: AgentReminder) -> AgentReminder | None:
    from datetime import timedelta

    from app.services.agent.schedule import MSK, next_weekly_run

    if reminder.recurrence == "daily":
        prev_msk = reminder.run_at.astimezone(MSK)
        next_run = (prev_msk + timedelta(days=1)).astimezone(timezone.utc)
        new_reminder = AgentReminder(
            agent_id=reminder.agent_id,
            run_at=next_run,
            message_text=reminder.message_text,
            recurrence="daily",
            status="pending",
        )
        db.add(new_reminder)
        await db.flush()
        return new_reminder

    if not reminder.recurrence or not reminder.recurrence.startswith("weekly:"):
        return None
    try:
        weekday = int(reminder.recurrence.split(":", 1)[1])
    except (IndexError, ValueError):
        return None

    prev_msk = reminder.run_at.astimezone(MSK)
    next_run = next_weekly_run(weekday, prev_msk.hour, prev_msk.minute, now=prev_msk)
    new_reminder = AgentReminder(
        agent_id=reminder.agent_id,
        run_at=next_run.astimezone(timezone.utc),
        message_text=reminder.message_text,
        recurrence=reminder.recurrence,
        status="pending",
    )
    db.add(new_reminder)
    await db.flush()
    return new_reminder


async def get_due_reminders(db: AsyncSession, *, limit: int = 50) -> list[AgentReminder]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AgentReminder)
        .join(AgentInstance)
        .where(
            AgentReminder.status == "pending",
            AgentReminder.run_at <= now,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
        .order_by(AgentReminder.run_at)
        .limit(limit)
    )
    return list(result.scalars().all())


def delivery_target(agent: AgentInstance) -> tuple[int | None, int | None]:
    """(user_id, chat_id) — куда слать в MAX."""
    if agent.role == AgentRole.PERSONAL_REMINDER.value:
        return agent.max_user_id, None
    if agent.role == AgentRole.GROUP_REMINDER.value:
        return None, agent.max_chat_id
    if agent.role == AgentRole.GROUP_MESSAGE_LOG.value:
        return agent.max_user_id, None
    return agent.max_user_id, None
