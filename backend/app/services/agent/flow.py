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
from app.services.agent.max_group import enrich_group_admin_status, check_user_is_group_admin
from app.services.agent.profile import agent_profile
from app.services.agent.lifecycle import cancel_agent, get_agent_for_thread
from app.services.agent.agent_loop import run_onboarding_loop
from app.services.agent.agent_orchestrator import user_wants_diagnostic
from app.services.agent.llm_onboarding import (
    apply_checklist_to_agent,
    build_confirmation_prompt,
    checklist_missing_fields,
    load_checklist,
    try_validate_checklist,
    user_wants_cancel,
)
from app.services.agent.max_probe import probe_max_chat
from app.services.bot import MaxBotService
from app.services.agent.onboarding import activation_summary
from app.services.agent.profile import EVENT_DRIVEN_ROLES, SCHEDULED_ROLES
from app.services.agent.knowledge import ingest_agent_files
from app.services.agent.reminders import activate_agent_reminders, effective_max_user_id
from app.services.agent.agent_status import (
    STATUS_ACTIVATING,
    STATUS_CONTEXT_RESET,
    STATUS_FIRST_DISPATCH,
    STATUS_INGEST_FILES,
    STATUS_PREFLIGHT,
    StatusCallback,
    emit_status,
    noop_status,
)
from app.services.agent.context_reset import (
    apply_onboarding_reset,
    context_reset_reply,
    is_pure_context_reset_request,
    mark_context_reset,
    user_wants_context_reset,
)
from app.services.agent.agent_pending import set_agent_pending

logger = logging.getLogger(__name__)


async def _assistant_reply(
    db: AsyncSession,
    thread: Thread,
    content: str,
    *,
    sources: list | None = None,
) -> Message:
    msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=content,
        sources=sources or None,
    )
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
    *,
    template: str | None = None,
) -> tuple[Thread, AgentInstance, Message]:
    from app.services.thread_factory import create_thread, next_agent_seq

    from app.services.agent.templates import get_template_title
    seq = await next_agent_seq(db, user.id)
    template_name = get_template_title(template)
    title = f"{template_name} {seq}" if template_name else f"Агент {seq}"
    thread = await create_thread(
        db,
        user_id=user.id,
        title=title,
        thread_type=ThreadType.AGENT,
        agent_seq=seq,
    )
    max_uid = int(user.max_user_id) if user.max_user_id else 0
    agent_config: dict = {"checklist": {}}
    if template:
        agent_config["template"] = template

    agent = AgentInstance(
        thread_id=thread.id,
        user_id=user.id,
        max_user_id=max_uid,
        status=AgentStatus.DRAFT.value,
        config=agent_config,
    )
    db.add(agent)
    await db.flush()

    from app.services.agent.templates import get_template_welcome
    welcome_text = get_template_welcome(template) or AGENT_WELCOME
    welcome = await _assistant_reply(db, thread, welcome_text)
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
    on_status: StatusCallback | None = None,
    reporter=None,
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
        raise ValueError("text_required_with_files")
    user_msg = await _user_message(db, thread, display_text)
    status_cb = on_status or noop_status
    await set_agent_pending(
        redis_client,
        thread_id,
        user_message_id=user_msg.id,
        phase="thinking",
        custom_status="Анализирую задачу…",
    )
    await emit_status(status_cb, "Анализирую задачу…")

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
            on_status=status_cb,
            reporter=reporter,
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
    on_status: StatusCallback | None = None,
    reporter=None,
) -> tuple[Message, Message, AgentInstance]:
    status_cb = on_status or noop_status
    file_hint = ""
    if file_ids:
        await emit_status(status_cb, STATUS_INGEST_FILES)
        # Читаем полный текст файлов ДО нарезки на чанки — для передачи в контекст LLM
        file_texts: list[str] = []
        try:
            from app.models.uploaded_file import UploadedFile
            from app.services.file_parser import extract_text as _extract_text
            from app.services.upload_storage import load_upload_bytes
            from sqlalchemy import select as _select
            files_result = await db.execute(
                _select(UploadedFile).where(
                    UploadedFile.user_id == user.id,
                    UploadedFile.id.in_(file_ids),
                )
            )
            for f in files_result.scalars().all():
                if (f.media_kind or "").lower() == "image":
                    continue
                raw_text = (f.extracted_text or "").strip()
                if not raw_text and f.storage_key:
                    data = await load_upload_bytes(f.storage_key)
                    raw_text = _extract_text(f.filename, data).strip()
                if raw_text:
                    file_texts.append(raw_text[:6000])
        except Exception as exc:
            logger.warning("File text extraction for hint failed: %s", exc)

        chunk_count = await ingest_agent_files(db, agent, user_id=user.id, file_ids=file_ids)
        if chunk_count:
            cfg = dict(agent.config or {})
            cfg["knowledge_chunk_count"] = chunk_count
            agent.config = cfg

        if file_texts:
            combined = "\n\n---\n\n".join(file_texts)
            file_hint = (
                f"\n\n[СИСТЕМНАЯ ПОДСКАЗКА: Пользователь загрузил файл. Содержимое файла:\n"
                f"```\n{combined}\n```\n"
                "Уточни у пользователя ОДНИМ вопросом: это ИНСТРУКЦИЯ для агента "
                "(сохранить через save_agent_instructions) "
                "или ДОПОЛНЕНИЕ К БАЗЕ ЗНАНИЙ (оставить как есть)?]"
            )

    if user_wants_cancel(text):
        await cancel_agent(db, agent, reason="user_cancel")
        assistant = await _assistant_reply(
            db,
            thread,
            (
                "Агент остановлен, напоминания отменены.\n\n"
                "Напишите новую задачу прямо здесь — начнём с чистого листа."
            ),
        )
        await db.commit()
        return user_msg, assistant, agent

    if agent.status == AgentStatus.CANCELLED.value:
        # Пользователь пишет в отменённый тред — перезапускаем агента здесь же
        from app.services.agent.lifecycle import reactivate_cancelled_agent
        await reactivate_cancelled_agent(db, agent)
        # Продолжаем обработку как обычный DRAFT

    context_reset = user_wants_context_reset(text)
    assistant_turn = False
    if context_reset:
        await emit_status(status_cb, STATUS_CONTEXT_RESET)
        mark_context_reset(agent, user_msg.id)
        if agent.status != AgentStatus.ACTIVE.value:
            apply_onboarding_reset(agent)
        else:
            assistant_turn = True
        if is_pure_context_reset_request(text):
            assistant = await _assistant_reply(db, thread, context_reset_reply(agent))
            await db.commit()
            return user_msg, assistant, agent
        assistant_turn = True

    diagnostic_mode = agent.status == AgentStatus.ACTIVE.value and (
        user_wants_diagnostic(text) or assistant_turn
    )

    # Активный агент продолжает диалог — не замораживаем.
    # diagnostic_mode=True позволяет использовать полный LLM-цикл с runtime-диагностикой.

    msgs_result = await db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.asc())
    )
    all_messages = list(msgs_result.scalars().all())
    try:
        llm_result = await run_onboarding_loop(
            db,
            redis_client,
            user,
            agent,
            all_messages,
            limiter,
            thread_id=thread.id,
            diagnostic_mode=diagnostic_mode,
            on_status=status_cb,
            reporter=reporter,
            file_hint=file_hint,
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
    was_active = agent.status == AgentStatus.ACTIVE.value
    apply_checklist_to_agent(agent, llm_result.checklist)
    if not diagnostic_mode and not was_active:
        agent.status = AgentStatus.COLLECTING.value

    cfg = dict(agent.config or {})
    await enrich_group_admin_status(agent, llm_result.checklist)
    if llm_result.checklist.bot_is_group_admin is not None:
        cfg["bot_is_group_admin"] = llm_result.checklist.bot_is_group_admin
        agent.config = cfg
    missing = checklist_missing_fields(llm_result.checklist)

    # LLM решает activate. Исключение: если все поля заполнены и пользователь явно подтверждает —
    # форсируем activate чтобы не застревать в бесконечном онбординге.
    should_activate = llm_result.activate
    if not should_activate and not missing and not was_active:
        from app.services.agent.llm_onboarding import user_wants_confirm
        if user_wants_confirm(text):
            logger.warning("AGENT_FLOW: force activate — missing=[], user confirmed, LLM missed it thread=%s", thread_id)
            should_activate = True

    logger.warning(
        "AGENT_FLOW: thread=%s should_activate=%s missing=%s checklist_role=%s checklist_chat_id=%s bot_admin=%s",
        thread_id, should_activate, missing,
        llm_result.checklist.role, llm_result.checklist.max_chat_id,
        llm_result.checklist.bot_is_group_admin,
    )

    if should_activate and not missing:
        try:
            try_validate_checklist(llm_result.checklist)
            if user.max_user_id:
                agent.max_user_id = int(user.max_user_id)
            elif not agent.max_user_id:
                raise ValueError("max_required")
            if agent.max_chat_id:
                await emit_status(status_cb, STATUS_PREFLIGHT)
                bot = MaxBotService()

                # Безопасность: пользователь должен быть администратором группы
                # чтобы не допустить публикации в чужие группы
                if user.max_user_id:
                    user_is_admin = await check_user_is_group_admin(
                        bot, int(agent.max_chat_id), int(user.max_user_id)
                    )
                    if user_is_admin is False:
                        cfg = dict(agent.config or {})
                        cfg["awaiting_confirmation"] = True
                        agent.config = cfg
                        await append_agent_activity_log(
                            db, agent, "user_not_group_admin",
                            details={"chat_id": agent.max_chat_id, "max_user_id": user.max_user_id},
                            level="error",
                        )
                        assistant = await _assistant_reply(
                            db,
                            thread,
                            (
                                "Не могу запустить агента: вы не являетесь администратором этой группы MAX.\n\n"
                                "Для публикации в группу вам нужны права администратора. "
                                "Попросите владельца группы выдать вам права, затем попробуйте снова."
                            ),
                        )
                        await db.commit()
                        return user_msg, assistant, agent
                    elif user_is_admin is None:
                        # Не удалось проверить — блокируем по умолчанию (fail closed).
                        # Бот не в группе или нет доступа к members — значит бот туда
                        # не был добавлен через стандартный путь (bot_added webhook).
                        cfg = dict(agent.config or {})
                        cfg["awaiting_confirmation"] = True
                        agent.config = cfg
                        await append_agent_activity_log(
                            db, agent, "user_admin_check_failed",
                            details={"chat_id": agent.max_chat_id, "reason": "cannot_verify"},
                            level="error",
                        )
                        assistant = await _assistant_reply(
                            db,
                            thread,
                            (
                                "Не удалось проверить ваши права в этой группе MAX.\n\n"
                                "Убедитесь что:\n"
                                "1. Вы являетесь администратором группы\n"
                                "2. Бот Glosix добавлен в группу как администратор\n\n"
                                "Затем напишите ссылку на группу снова или попробуйте ещё раз."
                            ),
                        )
                        await db.commit()
                        return user_msg, assistant, agent

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
            await emit_status(status_cb, STATUS_ACTIVATING)
            await activate_agent_reminders(db, agent)
            active_cfg = dict(agent.config or {})
            event_type = "agent_updated" if was_active else "agent_activated"
            await append_agent_activity_log(
                db,
                agent,
                event_type,
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
                    await emit_status(status_cb, STATUS_FIRST_DISPATCH)
                    sent = await dispatch_due_reminders(
                        db, agent_id=agent.id, redis_client=redis_client
                    )
                except Exception as exc:
                    logger.exception("Agent immediate dispatch failed agent=%s: %s", agent.id, exc)
                    sent = 0
                await db.commit()
            summary = activation_summary(agent)
            if was_active:
                summary = f"Настройки обновлены.\n\n{summary}"
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

    # Если LLM хотел активировать но есть незаполненные поля — показываем явную ошибку
    if should_activate and missing:
        logger.warning("Agent activation blocked: missing=%s thread=%s", missing, thread_id)
        if "bot_admin" in missing:
            error_reply = (
                "Не могу запустить агента: бот Glosix не является администратором группы MAX.\n\n"
                "Зайдите в настройки группы → Администраторы → добавьте бота Glosix как администратора. "
                "Затем напишите «да» снова."
            )
        elif "group_chat" in missing:
            error_reply = "Укажите ссылку на группу MAX (например, max.ru/-123456789)."
        else:
            error_reply = (
                f"Не хватает данных для запуска: {', '.join(missing)}. Уточните настройки и напишите «да» снова."
            )
        cfg["awaiting_confirmation"] = True
        agent.config = cfg
        assistant = await _assistant_reply(db, thread, error_reply)
        await db.commit()
        return user_msg, assistant, agent

    # Помечаем ожидание подтверждения для следующего сообщения
    if llm_result.ready_for_confirmation and not missing and not should_activate:
        cfg["awaiting_confirmation"] = True
    else:
        cfg["awaiting_confirmation"] = False
    agent.config = cfg

    assistant = await _assistant_reply(
        db,
        thread,
        llm_result.reply,
        sources=llm_result.sources,
    )
    await db.commit()
    return user_msg, assistant, agent
