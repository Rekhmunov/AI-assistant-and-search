"""Создание и отмена напоминаний агента."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.onboarding import validate_activation
from app.services.agent.profile import EVENT_DRIVEN_ROLES, SCHEDULED_ROLES, agent_profile
from app.services.agent.schedule import parse_reminder_schedule


async def cancel_reminders_for_agent(db: AsyncSession, agent_id: UUID) -> int:
    result = await db.execute(
        update(AgentReminder)
        .where(AgentReminder.agent_id == agent_id, AgentReminder.status == "pending")
        .values(status="cancelled")
        .returning(AgentReminder.id)
    )
    return len(result.scalars().all())


async def activate_agent_direct(db: AsyncSession, agent: AgentInstance) -> AgentReminder | None:
    """Activate a scheduled reminder agent bypassing full validate_activation (for API-created sub-reminders)."""
    await cancel_reminders_for_agent(db, agent.id)
    cfg = dict(agent.config or {})

    if agent.role not in SCHEDULED_ROLES:
        raise ValueError("role_unsupported")

    message_text = str(cfg.get("reminder_message") or cfg.get("image_prompt") or cfg.get("search_topic") or "—")
    run_at, recurrence = parse_reminder_schedule(
        str(cfg["schedule_text"]),
        tz_name=str(cfg.get("timezone") or "Europe/Moscow"),
    )
    reminder = AgentReminder(
        agent_id=agent.id,
        run_at=run_at,
        message_text=message_text,
        recurrence=recurrence,
        status="pending",
    )
    db.add(reminder)
    agent.status = AgentStatus.ACTIVE.value
    cfg["next_run_at"] = run_at.isoformat()
    agent.config = cfg
    await db.flush()
    return reminder


async def activate_agent(db: AsyncSession, agent: AgentInstance) -> AgentReminder | None:
    """Активирует агента: напоминание для scheduled-ролей или просто ACTIVE для event-driven."""
    validate_activation(agent)
    await cancel_reminders_for_agent(db, agent.id)
    cfg = dict(agent.config or {})
    profile = agent_profile(agent)

    if agent.role in EVENT_DRIVEN_ROLES:
        agent.status = AgentStatus.ACTIVE.value
        cfg.pop("next_run_at", None)
        agent.config = cfg
        await db.flush()
        return None

    if agent.role not in SCHEDULED_ROLES:
        raise ValueError("role_unsupported")

    message_text = str(cfg.get("reminder_message") or cfg.get("image_prompt") or cfg.get("search_topic") or "—")
    run_at, recurrence = parse_reminder_schedule(
        str(cfg["schedule_text"]),
        tz_name=str(cfg.get("timezone") or "Europe/Moscow"),
    )
    reminder = AgentReminder(
        agent_id=agent.id,
        run_at=run_at,
        message_text=message_text,
        recurrence=recurrence,
        status="pending",
    )
    db.add(reminder)
    agent.status = AgentStatus.ACTIVE.value
    cfg["next_run_at"] = run_at.isoformat()
    agent.config = cfg
    await db.flush()
    return reminder


async def activate_agent_reminders(db: AsyncSession, agent: AgentInstance) -> AgentReminder | None:
    return await activate_agent(db, agent)


async def schedule_next_recurrence(db: AsyncSession, reminder: AgentReminder) -> AgentReminder | None:
    from datetime import timedelta

    from app.services.agent.schedule import next_weekly_run, next_monthly_run, resolve_user_timezone

    agent_result = await db.get(AgentInstance, reminder.agent_id)
    tz_name = "Europe/Moscow"
    if agent_result and isinstance(agent_result.config, dict):
        tz_name = str(agent_result.config.get("timezone") or tz_name)
    user_tz = resolve_user_timezone(tz_name)

    if reminder.recurrence == "daily":
        prev_local = reminder.run_at.astimezone(user_tz)
        next_run = (prev_local + timedelta(days=1)).astimezone(timezone.utc)
        new_reminder = AgentReminder(
            agent_id=reminder.agent_id,
            run_at=next_run,
            message_text=reminder.message_text,
            recurrence="daily",
            status="pending",
        )
        db.add(new_reminder)
        if agent_result:
            cfg = dict(agent_result.config or {})
            cfg["next_run_at"] = next_run.isoformat()
            agent_result.config = cfg
        await db.flush()
        return new_reminder

    if reminder.recurrence == "hourly":
        next_run = reminder.run_at + timedelta(hours=1)
        new_reminder = AgentReminder(
            agent_id=reminder.agent_id,
            run_at=next_run,
            message_text=reminder.message_text,
            recurrence="hourly",
            status="pending",
        )
        db.add(new_reminder)
        if agent_result:
            cfg = dict(agent_result.config or {})
            cfg["next_run_at"] = next_run.isoformat()
            agent_result.config = cfg
        await db.flush()
        return new_reminder

    if reminder.recurrence and reminder.recurrence.startswith("monthly:"):
        try:
            day = int(reminder.recurrence.split(":", 1)[1])
        except (IndexError, ValueError):
            return None
        prev_local = reminder.run_at.astimezone(user_tz)
        next_run = next_monthly_run(day, prev_local.hour, prev_local.minute, now=prev_local, tz=user_tz)
        new_reminder = AgentReminder(
            agent_id=reminder.agent_id,
            run_at=next_run.astimezone(timezone.utc),
            message_text=reminder.message_text,
            recurrence=reminder.recurrence,
            status="pending",
        )
        db.add(new_reminder)
        if agent_result:
            cfg = dict(agent_result.config or {})
            cfg["next_run_at"] = next_run.astimezone(timezone.utc).isoformat()
            agent_result.config = cfg
        await db.flush()
        return new_reminder

    if reminder.recurrence in {"quarterly", "biannual", "yearly"}:
        from app.services.agent.schedule import next_interval_run
        months_map = {"quarterly": 3, "biannual": 6, "yearly": 12}
        months = months_map[reminder.recurrence]
        next_run = next_interval_run(reminder.run_at, months, tz=user_tz)
        new_reminder = AgentReminder(
            agent_id=reminder.agent_id,
            run_at=next_run.astimezone(timezone.utc),
            message_text=reminder.message_text,
            recurrence=reminder.recurrence,
            status="pending",
        )
        db.add(new_reminder)
        if agent_result:
            cfg = dict(agent_result.config or {})
            cfg["next_run_at"] = next_run.astimezone(timezone.utc).isoformat()
            agent_result.config = cfg
        await db.flush()
        return new_reminder

    if not reminder.recurrence or not reminder.recurrence.startswith("weekly:"):
        return None
    try:
        weekday = int(reminder.recurrence.split(":", 1)[1])
    except (IndexError, ValueError):
        return None

    prev_local = reminder.run_at.astimezone(user_tz)
    next_run = next_weekly_run(weekday, prev_local.hour, prev_local.minute, now=prev_local, tz=user_tz)
    new_reminder = AgentReminder(
        agent_id=reminder.agent_id,
        run_at=next_run.astimezone(timezone.utc),
        message_text=reminder.message_text,
        recurrence=reminder.recurrence,
        status="pending",
    )
    db.add(new_reminder)
    if agent_result:
        cfg = dict(agent_result.config or {})
        cfg["next_run_at"] = next_run.astimezone(timezone.utc).isoformat()
        agent_result.config = cfg
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


def effective_max_user_id(agent: AgentInstance) -> int | None:
    uid = int(agent.max_user_id) if agent.max_user_id else 0
    return uid if uid > 0 else None


def delivery_target(agent: AgentInstance) -> tuple[int | None, int | None]:
    """(user_id, chat_id) — куда слать в MAX."""
    max_uid = effective_max_user_id(agent)
    profile = agent_profile(agent)
    if profile.delivery_mode == "group":
        return None, agent.max_chat_id
    if agent.role == AgentRole.GROUP_REMINDER.value:
        return None, agent.max_chat_id
    return max_uid, None
