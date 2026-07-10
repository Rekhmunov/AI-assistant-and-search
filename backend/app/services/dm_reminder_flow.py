"""
SSE-флоу для создания напоминания из DM.
Роутер определяет intent create_reminder → этот флоу:
1. Извлекает текст и расписание из запроса через lite-LLM
2. Находит или создаёт hub-агент напоминаний у пользователя
3. Создаёт sub-agent напоминания с delivery_mode=dm
4. Возвращает SSE-ответ с подтверждением
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.thread import Thread, ThreadType
from app.models.user import User
from app.services.sse import sse_event

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """Извлеки из запроса пользователя параметры напоминания.

Верни ТОЛЬКО JSON:
{
  "reminder_text": "текст напоминания (что нужно сделать/о чём напомнить)",
  "schedule_text": "расписание на русском языке",
  "schedule_type": "one_time" | "daily" | "weekly" | "monthly"
}

Расписание должно быть строкой которую можно однозначно интерпретировать:
- "завтра в 10:00" → one_time
- "через 2 часа" → one_time
- "11 июля в 15:30" → one_time
- "каждый день в 9:00" → daily
- "каждый понедельник в 10:00" → weekly

Если время не указано → используй "завтра в 09:00".
Если пользователь не указал текст → используй суть запроса как текст.

Отвечай только JSON, без пояснений."""


async def stream_create_reminder_turn(
    db: AsyncSession,
    user: User,
    query: str,
    redis_client,
    llm,  # lite LLM для извлечения параметров
) -> AsyncIterator[str]:
    """SSE-поток создания напоминания из DM."""

    if not user.max_user_id:
        yield sse_event("token", {"text": (
            "Чтобы получать напоминания в MAX, привяжите аккаунт MAX в профиле.\n"
            "Перейдите в Профиль → Привязать MAX."
        )})
        yield sse_event("done", {"needs_search": False, "answer_model": "lite"})
        return

    # ── 1. Извлекаем текст и расписание через lite LLM ─────────────────────
    params = await _extract_reminder_params(llm, query)
    if not params:
        yield sse_event("token", {"text": (
            "Не удалось разобрать параметры напоминания. "
            "Попробуйте уточнить: «Напомни мне [что сделать] [когда]». "
            "Например: «Напомни мне позвонить маме завтра в 14:00»."
        )})
        yield sse_event("done", {"needs_search": False, "answer_model": "lite"})
        return

    reminder_text = params.get("reminder_text", query.strip())
    schedule_text = params.get("schedule_text", "завтра в 09:00")
    schedule_type = params.get("schedule_type", "one_time")

    # ── 2. Парсим расписание ────────────────────────────────────────────────
    try:
        from app.services.agent.schedule import parse_reminder_schedule, format_run_at_local
        run_at, recurrence = parse_reminder_schedule(schedule_text, tz_name="Europe/Moscow")
        time_str = format_run_at_local(run_at, "Europe/Moscow")
    except ValueError as exc:
        yield sse_event("token", {"text": (
            f"Не удалось разобрать время: «{schedule_text}». "
            "Попробуйте написать точнее, например: «завтра в 14:00» или «11 июля в 10:00»."
        )})
        yield sse_event("done", {"needs_search": False, "answer_model": "lite"})
        return

    # ── 3. Найти или создать hub-агент напоминаний ─────────────────────────
    hub_agent = await _find_or_create_reminder_hub(db, user)

    # ── 4. Создать sub-agent напоминания ───────────────────────────────────
    try:
        reminder = await _create_reminder_sub_agent(
            db, user, hub_agent,
            text=reminder_text,
            schedule_text=schedule_text,
            schedule_type=schedule_type,
            run_at=run_at,
            recurrence=recurrence,
        )
    except Exception as exc:
        logger.exception("dm_reminder_flow: failed to create reminder")
        yield sse_event("token", {"text": "Не удалось создать напоминание. Попробуйте ещё раз."})
        yield sse_event("done", {"needs_search": False, "answer_model": "lite"})
        return

    # ── 5. Подтверждение ───────────────────────────────────────────────────
    recurrence_hint = ""
    if recurrence:
        if recurrence == "daily":
            recurrence_hint = " (ежедневно)"
        elif recurrence.startswith("weekly:"):
            recurrence_hint = " (еженедельно)"
        elif recurrence.startswith("monthly:"):
            recurrence_hint = " (ежемесячно)"

    confirm = (
        f"✅ Напоминание создано\n"
        f"📝 {reminder_text}\n"
        f"🕐 {time_str}{recurrence_hint}"
    )

    yield sse_event("token", {"text": confirm})
    yield sse_event("done", {"needs_search": False, "answer_model": "lite"})


async def _extract_reminder_params(llm, query: str) -> dict | None:
    """Извлекает текст и расписание из запроса пользователя через lite LLM."""
    messages = [
        {"role": "system", "text": _EXTRACT_SYSTEM},
        {"role": "user", "text": query},
    ]
    try:
        raw = await llm.complete_text(messages, model="lite", max_tokens=256, temperature=0.0)
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if not m:
            return None
        return json.loads(m.group())
    except Exception:
        logger.warning("dm_reminder_flow: failed to extract params from %r", query[:100])
        return None


async def _find_or_create_reminder_hub(db: AsyncSession, user: User) -> AgentInstance:
    """Находит активный hub-агент напоминаний пользователя или создаёт новый."""
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.user_id == user.id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.config["template"].astext == "reminder",
            # Это hub, не sub-reminder
            AgentInstance.config["is_sub_reminder"].astext.is_(None),
        ).order_by(AgentInstance.created_at.asc())
    )
    hub = result.scalars().first()

    # Попробуем через is_sub_reminder = false
    if not hub:
        result2 = await db.execute(
            select(AgentInstance).where(
                AgentInstance.user_id == user.id,
                AgentInstance.status == AgentStatus.ACTIVE.value,
                AgentInstance.config["template"].astext == "reminder",
            ).order_by(AgentInstance.created_at.asc())
        )
        for agent in result2.scalars().all():
            cfg = agent.config or {}
            if not cfg.get("is_sub_reminder"):
                hub = agent
                break

    if hub:
        return hub

    # Создаём новый hub
    from app.services.agent.flow import create_agent_thread
    from sqlalchemy.orm.attributes import flag_modified
    thread, agent, _ = await create_agent_thread(db, user, template="reminder")
    # Hub активируем сразу — не требует подключения внешних каналов
    agent.status = AgentStatus.ACTIVE.value
    # Снимаем is_new — напоминание создано через DM, уже есть действие
    cfg = dict(agent.config or {})
    cfg.pop("is_new", None)
    agent.config = cfg
    flag_modified(agent, "config")
    await db.commit()
    await db.refresh(agent)
    return agent


async def _create_reminder_sub_agent(
    db: AsyncSession,
    user: User,
    hub: AgentInstance,
    *,
    text: str,
    schedule_text: str,
    schedule_type: str,
    run_at: datetime,
    recurrence: str | None,
) -> AgentInstance:
    """Создаёт sub-agent напоминания с delivery_mode=dm."""
    from app.services.thread_factory import create_thread, next_agent_seq
    from app.services.agent.reminders import activate_agent_direct
    from sqlalchemy.orm.attributes import flag_modified

    seq = await next_agent_seq(db, user.id)
    sub_thread = await create_thread(
        db,
        user_id=user.id,
        title=f"Напоминание {seq}",
        thread_type=ThreadType.AGENT,
        agent_seq=seq,
    )

    max_uid = int(user.max_user_id) if user.max_user_id else 0
    sub_cfg: dict = {
        "template": "reminder",
        "is_sub_reminder": True,
        "parent_hub_id": str(hub.id),
        "reminder_name": text[:60],
        "reminder_message": text,
        "schedule_text": schedule_text,
        "schedule_type": schedule_type,
        "schedule_time": run_at.strftime("%H:%M"),
        "schedule_weekday": "",
        "schedule_day_of_month": None,
        "schedule_date": run_at.strftime("%Y-%m-%d"),
        "schedule_interval_value": None,
        "schedule_interval_unit": "minutes",
        "delivery_mode": "dm",
        "timezone": "Europe/Moscow",
        "next_run_at": run_at.isoformat(),
        "recurrence_stored": recurrence,
    }

    sub_agent = AgentInstance(
        thread_id=sub_thread.id,
        user_id=user.id,
        max_user_id=max_uid,
        role=AgentRole.DM_ASSISTANT.value,
        status=AgentStatus.DRAFT.value,
        config=sub_cfg,
    )
    db.add(sub_agent)
    await db.flush()

    await activate_agent_direct(db, sub_agent)

    # Снимаем is_new с hub если вдруг стоит
    hub_cfg = dict(hub.config or {})
    if hub_cfg.pop("is_new", None) is not None:
        hub.config = hub_cfg
        flag_modified(hub, "config")

    await db.commit()
    await db.refresh(sub_agent)
    return sub_agent
