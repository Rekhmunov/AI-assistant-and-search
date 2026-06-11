"""Обработка сообщений в треде агента (LLM-диалог, без поискового SSE)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import User
from app.services.agent.constants import AGENT_WELCOME
from app.services.agent.activity_log import append_agent_activity_log
from app.services.agent.dispatch import dispatch_due_reminders
from app.services.agent.max_group import enrich_group_admin_status
from app.services.agent.profile import agent_profile
from app.services.agent.lifecycle import cancel_agent, get_agent_for_thread
from app.services.agent.capabilities import reply_claims_activation
from app.services.agent.intent_hints import user_wants_immediate_run, user_wants_today_run
from app.services.agent.agent_orchestrator import run_agent_turn, user_wants_diagnostic
from app.services.agent.operational import handle_operational_query, is_operational_max_query
from app.services.agent.llm_onboarding import (
    apply_checklist_to_agent,
    build_confirmation_prompt,
    build_parse_fallback_reply,
    checklist_missing_fields,
    load_checklist,
    try_validate_checklist,
    user_wants_cancel,
    user_wants_confirm,
)
from app.services.agent.max_probe import probe_max_chat
from app.services.bot import MaxBotService
from app.services.agent.onboarding import activation_summary
from app.services.agent.profile import EVENT_DRIVEN_ROLES, SCHEDULED_ROLES
from app.services.agent.knowledge import ingest_agent_files
from app.services.agent.reminders import activate_agent_reminders, effective_max_user_id

logger = logging.getLogger(__name__)


async def _assistant_reply(db: AsyncSession, thread: Thread, content: str) -> Message:
    msg = Message(thread_id=thread.id, role=MessageRole.ASSISTANT, content=content)
    db.add(msg)
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


async def _user_message(db: AsyncSession, thread: Thread, content: str) -> Message:
    msg = Message(thread_id=thread.id, role=MessageRole.USER, content=content)
    db.add(msg)
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


async def create_agent_thread(
    db: AsyncSession,
    user: User,
) -> tuple[Thread, AgentInstance, Message]:
    from app.services.thread_factory import create_thread, next_agent_seq

    seq = await next_agent_seq(db, user.id)
    title = f"Агент {seq}"
    thread = await create_thread(
        db,
        user_id=user.id,
        title=title,
        thread_type=ThreadType.AGENT,
        agent_seq=seq,
    )
    max_uid = int(user.max_user_id) if user.max_user_id else 0
    agent = AgentInstance(
        thread_id=thread.id,
        user_id=user.id,
        max_user_id=max_uid,
        status=AgentStatus.DRAFT.value,
        config={"checklist": {}},
    )
    db.add(agent)
    await db.flush()

    welcome = await _assistant_reply(db, thread, AGENT_WELCOME)
    return thread, agent, welcome


async def handle_agent_message(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    thread_id: UUID,
    text: str,
    redis_client,
    *,
    file_ids: list[UUID] | None = None,
) -> tuple[Message, Message, AgentInstance]:
    result = await db.execute(
        select(Thread)
        .where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.thread_type == ThreadType.AGENT,
        )
        .options(selectinload(Thread.messages))
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise ValueError("thread_not_found")

    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise ValueError("agent_not_found")

    if agent.user_id != user.id:
        raise ValueError("agent_owner_mismatch")

    if agent.max_user_id and user.max_user_id and agent.max_user_id != int(user.max_user_id):
        raise ValueError("max_user_mismatch")

    allowed, _used, _limit = await limiter.check_search_limit(str(user.id), user.plan)
    if not allowed:
        raise ValueError("rate_limit")

    display_text = text.strip()
    if file_ids and not display_text:
        display_text = f"[Загружено документов: {len(file_ids)}]"
    user_msg = await _user_message(db, thread, display_text)

    try:
        return await _handle_agent_message_body(
            db,
            user,
            thread,
            agent,
            thread_id,
            text,
            redis_client,
            user_msg,
            limiter,
            file_ids=file_ids,
        )
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("Agent message unhandled error thread=%s: %s", thread_id, exc)
        await db.rollback()
        assistant = await _assistant_reply(
            db,
            thread,
            (
                "Сейчас не удалось обработать запрос. Попробуйте ещё раз через несколько секунд "
                "или переформулируйте задачу."
            ),
        )
        await db.commit()
        return user_msg, assistant, agent


async def _handle_agent_message_body(
    db: AsyncSession,
    user: User,
    thread: Thread,
    agent: AgentInstance,
    thread_id: UUID,
    text: str,
    redis_client,
    user_msg: Message,
    limiter: RateLimiter,
    *,
    file_ids: list[UUID] | None = None,
) -> tuple[Message, Message, AgentInstance]:
    if file_ids:
        chunk_count = await ingest_agent_files(db, agent, user_id=user.id, file_ids=file_ids)
        if chunk_count:
            cfg = dict(agent.config or {})
            cfg["knowledge_chunk_count"] = chunk_count
            agent.config = cfg

    if user_wants_cancel(text):
        await cancel_agent(db, agent, reason="user_cancel")
        assistant = await _assistant_reply(
            db,
            thread,
            "Агент остановлен. Напоминания отменены. Создайте нового агента, если понадобится снова.",
        )
        await db.commit()
        return user_msg, assistant, agent

    if agent.status == AgentStatus.CANCELLED.value:
        assistant = await _assistant_reply(
            db,
            thread,
            "Этот агент уже отключён. Нажмите иконку робота, чтобы создать нового.",
        )
        await db.commit()
        return user_msg, assistant, agent

    operational = is_operational_max_query(text)
    diagnostic_mode = agent.status == AgentStatus.ACTIVE.value and (
        user_wants_diagnostic(text) or operational
    )

    op_handled = await handle_operational_query(
        db, user, agent, thread, text, user_msg=user_msg
    )
    if op_handled is not None:
        return op_handled

    if agent.status == AgentStatus.ACTIVE.value and not diagnostic_mode:
        assistant = await _assistant_reply(
            db,
            thread,
            (
                "Агент уже работает.\n"
                f"{activation_summary(agent)}\n\n"
                "Чтобы изменить параметры, отключите агента фразой «отключи агента» и создайте нового.\n"
                "Если что-то не так с отправкой — спросите «почему не отправляет» или «проверь группу»."
            ),
        )
        await db.commit()
        return user_msg, assistant, agent

    msgs_result = await db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.asc())
    )
    all_messages = list(msgs_result.scalars().all())
    try:
        llm_result = await run_agent_turn(
            db,
            redis_client,
            user,
            agent,
            all_messages,
            limiter,
            thread_id=thread.id,
            diagnostic_mode=diagnostic_mode,
        )
    except Exception as exc:
        logger.exception("Agent LLM turn failed thread=%s", thread_id)
        assistant = await _assistant_reply(
            db,
            thread,
            (
                "Сейчас не удалось обработать запрос. Попробуйте ещё раз через минуту "
                "или переформулируйте задачу для агента."
            ),
        )
        await db.commit()
        return user_msg, assistant, agent
    apply_checklist_to_agent(agent, llm_result.checklist)
    if not diagnostic_mode:
        agent.status = AgentStatus.COLLECTING.value

    cfg = dict(agent.config or {})
    await enrich_group_admin_status(agent, llm_result.checklist)
    if llm_result.checklist.bot_is_group_admin is not None:
        cfg["bot_is_group_admin"] = llm_result.checklist.bot_is_group_admin
        agent.config = cfg
    missing = checklist_missing_fields(llm_result.checklist)

    should_activate = llm_result.activate
    if not should_activate and not missing:
        if user_wants_confirm(text) and (
            cfg.get("awaiting_confirmation") or llm_result.ready_for_confirmation
        ):
            should_activate = True
        elif user_wants_today_run(text) or user_wants_immediate_run(text):
            should_activate = True

    if should_activate and not missing:
        try:
            try_validate_checklist(llm_result.checklist)
            if user.max_user_id:
                agent.max_user_id = int(user.max_user_id)
            elif not agent.max_user_id:
                raise ValueError("max_required")
            if agent.max_chat_id:
                bot = MaxBotService()
                probe = await probe_max_chat(bot, int(agent.max_chat_id), send_test=False)
                await append_agent_activity_log(
                    db,
                    agent,
                    "preflight_on_activate",
                    details=probe,
                    level="info" if probe.get("ok") else "error",
                )
                if not probe.get("ok"):
                    explanation = probe.get("explanation") or "Не удалось проверить группу MAX."
                    cfg = dict(agent.config or {})
                    cfg["awaiting_confirmation"] = True
                    agent.config = cfg
                    assistant = await _assistant_reply(
                        db,
                        thread,
                        f"Перед запуском проверил группу MAX:\n\n{explanation}",
                    )
                    await db.commit()
                    return user_msg, assistant, agent
            await activate_agent_reminders(db, agent)
            active_cfg = dict(agent.config or {})
            await append_agent_activity_log(
                db,
                agent,
                "agent_activated",
                details={
                    "role": agent.role,
                    "schedule": active_cfg.get("schedule_text"),
                    "max_chat_id": agent.max_chat_id,
                    "next_run_at": active_cfg.get("next_run_at"),
                },
            )
            await db.commit()
            sent = 0
            if agent.role in SCHEDULED_ROLES:
                try:
                    sent = await dispatch_due_reminders(
                        db, agent_id=agent.id, redis_client=redis_client
                    )
                except Exception as exc:
                    logger.exception("Agent immediate dispatch failed agent=%s: %s", agent.id, exc)
                    sent = 0
                await db.commit()
            summary = activation_summary(agent)
            if agent.role in SCHEDULED_ROLES:
                if sent:
                    summary += "\n\nПервый запуск уже выполнен — проверьте MAX."
                else:
                    summary += "\n\nЗапуск запланирован — бот напишет в MAX в указанное время."
                    profile = agent_profile(agent)
                    if profile.delivery_mode == "group":
                        if not agent.max_chat_id:
                            summary += (
                                "\n\n⚠️ ID группы MAX не указан — сообщения в группу не дойдут."
                            )
                    elif not effective_max_user_id(agent):
                        summary += (
                            "\n\n⚠️ Аккаунт MAX не привязан — привяжите в Профиле, "
                            "иначе сообщения не дойдут."
                        )
            elif agent.role in EVENT_DRIVEN_ROLES:
                summary += "\n\nАгент слушает события в MAX — дополнительных действий не требуется."
            assistant = await _assistant_reply(db, thread, summary)
            await db.commit()
            return user_msg, assistant, agent
        except ValueError as exc:
            logger.warning("Agent activation validation failed: %s", exc)
            code = str(exc)
            if code in {"schedule_unparseable", "schedule_missing"}:
                error_reply = (
                    "Не удалось разобрать расписание. Напишите, когда срабатывать — "
                    "например «каждый час», «каждый день в 16:35» или «через 30 минут»."
                )
            elif code == "max_required":
                error_reply = (
                    "Сначала привяжите MAX: откройте **Профиль** в Glosix и войдите через MAX."
                )
            elif code == "message_missing":
                error_reply = "Укажите текст сообщения, которое бот будет отправлять."
            else:
                error_reply = (
                    "Не удалось запустить агента. Проверьте настройки и попробуйте снова."
                )
            cfg["awaiting_confirmation"] = True
            agent.config = cfg
            assistant = await _assistant_reply(db, thread, error_reply)
            await db.commit()
            return user_msg, assistant, agent
        except Exception as exc:
            logger.exception("Agent activation failed thread=%s: %s", thread_id, exc)
            cfg["awaiting_confirmation"] = True
            agent.config = cfg
            assistant = await _assistant_reply(
                db,
                thread,
                (
                    "Настройки сохранены, но запустить агента сейчас не удалось. "
                    "Попробуйте написать «да» ещё раз через минуту."
                ),
            )
            await db.commit()
            return user_msg, assistant, agent

    if should_activate and missing:
        llm_result.reply = build_parse_fallback_reply(
            llm_result.checklist.to_dict(),
            text,
        )
    elif reply_claims_activation(llm_result.reply) and not should_activate:
        llm_result.reply = (
            build_confirmation_prompt(
                llm_result.confirmation_summary,
                llm_result.checklist,
            )
            if not missing
            else build_parse_fallback_reply(llm_result.checklist.to_dict(), text)
        )

    if llm_result.ready_for_confirmation and not missing and not should_activate:
        cfg["awaiting_confirmation"] = True
        agent.config = cfg
        if "подтверж" not in llm_result.reply.lower() and "запустить" not in llm_result.reply.lower():
            llm_result.reply = build_confirmation_prompt(
                llm_result.confirmation_summary,
                llm_result.checklist,
            )
    else:
        cfg["awaiting_confirmation"] = False
        agent.config = cfg

    assistant = await _assistant_reply(db, thread, llm_result.reply)
    await db.commit()
    return user_msg, assistant, agent
