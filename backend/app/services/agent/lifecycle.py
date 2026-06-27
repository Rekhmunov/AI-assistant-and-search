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
    is_assistant = str((agent.config or {}).get("template") or "") == "assistant"
    await cancel_reminders_for_agent(db, agent.id)
    await db.delete(agent)
    await db.flush()
    if is_assistant:
        await _clear_assistant_bot_commands()
    return True


async def _clear_assistant_bot_commands() -> None:
    """Снимает регистрацию slash-команд ассистента в MAX при деактивации."""
    try:
        from app.services.bot import MaxBotService
        bot = MaxBotService()
        await bot.set_commands([])
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("_clear_assistant_bot_commands failed: %s", exc)


async def on_thread_soft_deleted(db: AsyncSession, thread: Thread) -> None:
    if thread.thread_type != "agent":
        return
    # First, cancel any sub-reminders linked to this hub
    await _cancel_sub_reminders_for_hub(db, thread.id)
    await purge_agent_for_thread(db, thread.id)


async def _cancel_sub_reminders_for_hub(db: AsyncSession, hub_thread_id: "UUID") -> None:
    """Cancel all sub-reminder agents whose parent hub is being deleted."""
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select as _sel

    # Find hub agent
    hub_result = await db.execute(
        _sel(AgentInstance).where(AgentInstance.thread_id == hub_thread_id)
    )
    hub_agent = hub_result.scalar_one_or_none()
    if not hub_agent:
        return
    hub_cfg = dict(hub_agent.config or {})
    if hub_cfg.get("template") != "reminder":
        return

    # Find all sub-agents
    from app.models.thread import Thread as _Thread
    sub_result = await db.execute(
        _sel(AgentInstance).where(
            AgentInstance.config["parent_hub_id"].astext == str(hub_agent.id)
        )
    )
    sub_agents = list(sub_result.scalars().all())
    from app.services.agent.reminders import cancel_reminders_for_agent
    now = datetime.now(_tz.utc)
    for sub in sub_agents:
        await cancel_reminders_for_agent(db, sub.id)
        sub.status = AgentStatus.CANCELLED.value
        # Soft-delete the sub-thread too
        sub_thread_result = await db.execute(
            _sel(_Thread).where(_Thread.id == sub.thread_id)
        )
        sub_thread = sub_thread_result.scalar_one_or_none()
        if sub_thread:
            sub_thread.deleted_at = now
    await db.flush()


async def reactivate_cancelled_agent(db: AsyncSession, agent: AgentInstance) -> None:
    """
    Сбрасывает отменённый агент в DRAFT — пользователь может начать новую задачу
    в том же треде без создания нового агента.
    """
    from app.services.agent.llm_onboarding import ChecklistState

    agent.status = AgentStatus.DRAFT.value
    agent.role = None
    agent.max_chat_id = None
    agent.instruction_text = ""
    cfg = dict(agent.config or {})
    cfg["checklist"] = ChecklistState().to_dict()
    cfg.pop("schedule_text", None)
    cfg.pop("reminder_message", None)
    cfg.pop("next_run_at", None)
    cfg.pop("last_dispatch_error", None)
    cfg.pop("cancel_reason", None)
    cfg.pop("awaiting_confirmation", None)
    agent.config = cfg
    await db.flush()
