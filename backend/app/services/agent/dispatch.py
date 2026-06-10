"""Немедленная отправка напоминаний (не ждать Celery beat)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentStatus
from app.models.user import User
from app.services.agent.activity_log import append_agent_activity_log
from app.services.agent.content import build_delivery_content
from app.services.agent.max_compliance import dispatch_stagger
from app.services.agent.max_errors import explain_max_send_error
from app.services.agent.max_probe import probe_max_chat
from app.services.agent.profile import agent_profile
from app.services.agent.reminders import delivery_target, schedule_next_recurrence
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def _resolve_user(db: AsyncSession, agent: AgentInstance) -> User | None:
    result = await db.execute(select(User).where(User.id == agent.user_id))
    return result.scalar_one_or_none()


def _delivery_ready(agent: AgentInstance) -> tuple[bool, str | None]:
    profile = agent_profile(agent)
    user_id, chat_id = delivery_target(agent)
    if profile.delivery_mode == "group" or chat_id is not None:
        if not chat_id:
            return False, "max_chat_id missing"
        return True, None
    if not user_id:
        return False, "max_user_id missing"
    return True, None


async def _record_dispatch_error(agent: AgentInstance, error: str, explanation: str) -> None:
    cfg = dict(agent.config or {})
    cfg["last_dispatch_error"] = error[:500]
    cfg["last_dispatch_explanation"] = explanation[:800]
    cfg["last_dispatch_at"] = datetime.now(timezone.utc).isoformat()
    agent.config = cfg


async def dispatch_due_reminders(
    db: AsyncSession,
    *,
    agent_id: UUID | None = None,
    bot: MaxBotService | None = None,
    redis_client=None,
    limit: int = 20,
    skip_preflight: bool = False,
) -> int:
    """Отправляет просроченные pending-напоминания. Возвращает число обработанных."""
    bot = bot or MaxBotService()
    redis_owned = False
    if redis_client is None:
        import redis.asyncio as aioredis

        from app.core.config import get_settings

        redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        redis_owned = True
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

    for index, reminder in enumerate(reminders):
        await dispatch_stagger(index)
        agent_result = await db.execute(
            select(AgentInstance).where(AgentInstance.id == reminder.agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent or agent.status != AgentStatus.ACTIVE.value:
            reminder.status = "cancelled"
            continue

        ready, ready_err = _delivery_ready(agent)
        if not ready:
            reminder.last_error = ready_err
            reminder.status = "failed"
            explanation = explain_max_send_error(ready_err, chat_id=agent.max_chat_id)
            await _record_dispatch_error(agent, ready_err or "", explanation)
            logger.warning(
                "Agent reminder skipped: %s agent=%s reminder=%s",
                ready_err,
                agent.id,
                reminder.id,
            )
            await append_agent_activity_log(
                db,
                agent,
                "dispatch_skipped",
                reminder_id=reminder.id,
                details={"error": ready_err, "explanation": explanation},
                level="error",
            )
            if reminder.recurrence:
                await schedule_next_recurrence(db, reminder)
            continue

        user = await _resolve_user(db, agent)
        if not user:
            reminder.last_error = "user missing"
            reminder.status = "failed"
            await append_agent_activity_log(
                db,
                agent,
                "dispatch_skipped",
                reminder_id=reminder.id,
                details={"error": "user missing"},
                level="error",
            )
            if reminder.recurrence:
                await schedule_next_recurrence(db, reminder)
            continue

        user_id, chat_id = delivery_target(agent)

        if chat_id and not skip_preflight:
            probe = await probe_max_chat(bot, int(chat_id), send_test=False)
            if not probe.get("ok"):
                err = str(probe.get("error") or "preflight_failed")
                explanation = str(probe.get("explanation") or explain_max_send_error(err, chat_id=chat_id))
                reminder.last_error = err[:500]
                await _record_dispatch_error(agent, err, explanation)
                await append_agent_activity_log(
                    db,
                    agent,
                    "preflight_failed",
                    reminder_id=reminder.id,
                    details={"error": err, "explanation": explanation, "probe": probe},
                    level="error",
                )
                if probe.get("status") in {"removed", "left", "closed"}:
                    reminder.status = "failed"
                    if reminder.recurrence:
                        await schedule_next_recurrence(db, reminder)
                    continue
                reminder.run_at = now + timedelta(minutes=10)
                continue

        await append_agent_activity_log(
            db,
            agent,
            "dispatch_started",
            reminder_id=reminder.id,
            details={
                "run_at": reminder.run_at.isoformat(),
                "chat_id": chat_id,
                "user_id": user_id,
                "recurrence": reminder.recurrence,
            },
        )
        try:
            content = await build_delivery_content(
                db,
                redis_client,
                user,
                agent,
                reminder,
                bot=bot,
            )
        except Exception as exc:
            logger.exception("Agent content build failed agent=%s: %s", agent.id, exc)
            err = str(exc)[:500]
            reminder.last_error = err
            explanation = f"Не удалось подготовить контент: {err}"
            await _record_dispatch_error(agent, err, explanation)
            reminder.status = "failed"
            await append_agent_activity_log(
                db,
                agent,
                "content_build_failed",
                reminder_id=reminder.id,
                details={"error": err, "explanation": explanation},
                level="error",
            )
            if reminder.recurrence:
                await schedule_next_recurrence(db, reminder)
            continue

        await append_agent_activity_log(
            db,
            agent,
            "content_ready",
            reminder_id=reminder.id,
            details={
                "text_len": len(content.text or ""),
                "attachments": len(content.attachments or []),
            },
        )

        send_result = await bot.send_message(
            int(user_id) if user_id else None,
            content.text,
            attachments=content.attachments or None,
            chat_id=int(chat_id) if chat_id else None,
        )
        if send_result.ok:
            reminder.status = "sent"
            reminder.sent_at = datetime.now(timezone.utc)
            next_reminder = await schedule_next_recurrence(db, reminder)
            sent_count += 1
            cfg = dict(agent.config or {})
            cfg.pop("last_dispatch_error", None)
            cfg.pop("last_dispatch_explanation", None)
            agent.config = cfg
            logger.info("Agent reminder sent agent=%s reminder=%s", agent.id, reminder.id)
            await append_agent_activity_log(
                db,
                agent,
                "dispatch_sent",
                reminder_id=reminder.id,
                details={
                    "max_message_id": send_result.message_id,
                    "next_run_at": next_reminder.run_at.isoformat() if next_reminder else None,
                },
            )
        else:
            raw_err = (send_result.error or "send failed")[:500]
            explanation = explain_max_send_error(raw_err, chat_id=chat_id, user_id=user_id)
            reminder.last_error = raw_err
            await _record_dispatch_error(agent, raw_err, explanation)
            logger.warning(
                "Agent reminder failed agent=%s reminder=%s err=%s",
                agent.id,
                reminder.id,
                reminder.last_error,
            )
            await append_agent_activity_log(
                db,
                agent,
                "dispatch_failed",
                reminder_id=reminder.id,
                details={"error": raw_err, "explanation": explanation},
                level="error",
            )
            if send_result.retry_after_sec:
                reminder.run_at = now + timedelta(seconds=send_result.retry_after_sec)
            else:
                reminder.status = "failed"
                if reminder.recurrence:
                    await schedule_next_recurrence(db, reminder)

    if reminders:
        await db.flush()
    if redis_owned:
        await redis_client.aclose()
    return sent_count
