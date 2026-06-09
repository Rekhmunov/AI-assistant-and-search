"""Celery: отправка напоминаний агентов в MAX."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.reminders import delivery_target, schedule_next_recurrence
from app.services.bot import MaxBotService
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="dispatch_agent_reminders")
def dispatch_agent_reminders_task() -> None:
    asyncio.run(_dispatch_agent_reminders_async())


async def _dispatch_agent_reminders_async() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    bot = MaxBotService()

    async with session_factory() as db:
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
            .limit(100)
        )
        reminders = list(result.scalars().all())

        for reminder in reminders:
            agent_result = await db.execute(
                select(AgentInstance).where(AgentInstance.id == reminder.agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if not agent or agent.status != AgentStatus.ACTIVE.value:
                reminder.status = "cancelled"
                continue

            user_id, chat_id = delivery_target(agent)
            text = reminder.message_text

            if agent.role == AgentRole.GROUP_MESSAGE_LOG.value:
                cfg = dict(agent.config or {})
                buffer = cfg.get("message_buffer") or []
                if not buffer:
                    text = "Новых сообщений в группе с прошлой сводки нет."
                else:
                    lines = [f"• {item.get('author', '?')}: {item.get('text', '')[:200]}" for item in buffer[-20:]]
                    text = f"{reminder.message_text}\n\n" + "\n".join(lines)
                    cfg["message_buffer"] = []
                    agent.config = cfg

            send_result = await bot.send_message(
                user_id,
                text,
                chat_id=chat_id,
            )
            if send_result.ok:
                reminder.status = "sent"
                reminder.sent_at = datetime.now(timezone.utc)
                await schedule_next_recurrence(db, reminder)
            else:
                reminder.last_error = (send_result.error or "send failed")[:500]
                if send_result.retry_after_sec:
                    reminder.run_at = now + timedelta(seconds=send_result.retry_after_sec)
                else:
                    reminder.status = "failed"

        await db.commit()

    await engine.dispose()
