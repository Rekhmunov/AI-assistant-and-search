"""Немедленная отправка напоминаний (не ждать Celery beat)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.reminders import delivery_target, schedule_next_recurrence
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def dispatch_due_reminders(
    db: AsyncSession,
    *,
    agent_id: UUID | None = None,
    bot: MaxBotService | None = None,
    limit: int = 20,
) -> int:
    """Отправляет просроченные pending-напоминания. Возвращает число обработанных."""
    bot = bot or MaxBotService()
    now = datetime.now(timezone.utc)
    q = (
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
    if agent_id is not None:
        q = q.where(AgentInstance.id == agent_id)

    result = await db.execute(q)
    reminders = list(result.scalars().all())
    sent_count = 0

    for reminder in reminders:
        agent_result = await db.execute(
            select(AgentInstance).where(AgentInstance.id == reminder.agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent or agent.status != AgentStatus.ACTIVE.value:
            reminder.status = "cancelled"
            continue

        max_uid = int(agent.max_user_id) if agent.max_user_id else 0
        if max_uid <= 0:
            reminder.last_error = "max_user_id missing"
            reminder.status = "failed"
            logger.warning("Agent reminder skipped: no max_user_id agent=%s", agent.id)
            continue

        user_id, chat_id = delivery_target(agent)
        text = reminder.message_text

        if agent.role == AgentRole.GROUP_MESSAGE_LOG.value:
            cfg = dict(agent.config or {})
            buffer = cfg.get("message_buffer") or []
            if not buffer:
                text = "Новых сообщений в группе с прошлой сводки нет."
            else:
                lines = [
                    f"• {item.get('author', '?')}: {item.get('text', '')[:200]}"
                    for item in buffer[-20:]
                ]
                text = f"{reminder.message_text}\n\n" + "\n".join(lines)
                cfg["message_buffer"] = []
                agent.config = cfg

        send_result = await bot.send_message(
            int(user_id) if user_id else None,
            text,
            chat_id=int(chat_id) if chat_id else None,
        )
        if send_result.ok:
            reminder.status = "sent"
            reminder.sent_at = datetime.now(timezone.utc)
            await schedule_next_recurrence(db, reminder)
            sent_count += 1
            logger.info("Agent reminder sent agent=%s reminder=%s", agent.id, reminder.id)
        else:
            reminder.last_error = (send_result.error or "send failed")[:500]
            logger.warning(
                "Agent reminder failed agent=%s reminder=%s err=%s",
                agent.id,
                reminder.id,
                reminder.last_error,
            )
            if send_result.retry_after_sec:
                reminder.run_at = now + timedelta(seconds=send_result.retry_after_sec)
            else:
                reminder.status = "failed"

    if reminders:
        await db.flush()
    return sent_count
