"""Celery: отправка напоминаний агентов в MAX и фоновый agent loop."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.agent import AgentInstance
from app.models.user import User
from app.services.agent.activity_log import purge_old_agent_activity_logs
from app.services.agent.agent_runtime import deliver_runtime_result, run_max_interactive_loop
from app.services.agent.dispatch import dispatch_due_reminders
from app.services.agent.reminders import get_due_reminders
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

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    count = 0
    due_count = 0
    try:
        async with session_factory() as db:
            due = await get_due_reminders(db, limit=100)
            due_count = len(due)
            count = await dispatch_due_reminders(db, redis_client=redis_client, limit=50)
            await db.commit()
    except Exception:
        logger.exception("Celery dispatch_agent_reminders failed")
        raise
    finally:
        await redis_client.aclose()
    logger.info(
        "Celery dispatch_agent_reminders: due=%s dispatched=%s",
        due_count,
        count,
    )
    await engine.dispose()


@celery.task(name="purge_agent_activity_logs")
def purge_agent_activity_logs_task() -> None:
    asyncio.run(_purge_agent_activity_logs_async())


async def _purge_agent_activity_logs_async() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            deleted, messages_removed = await purge_old_agent_activity_logs(db)
            await db.commit()
        logger.info(
            "purge_agent_activity_logs: deleted=%s messages_removed=%s",
            deleted,
            messages_removed,
        )
    except Exception:
        logger.exception("purge_agent_activity_logs failed")
        raise
    finally:
        await engine.dispose()


def enqueue_max_agent_loop_background(
    *,
    agent_id: str,
    user_id: str,
    user_text: str,
    chat_id: int,
    author: str = "",
    vision_context: str = "",
) -> None:
    run_max_agent_loop_background_task.delay(
        agent_id=agent_id,
        user_id=user_id,
        user_text=user_text,
        chat_id=chat_id,
        author=author,
        vision_context=vision_context,
    )


@celery.task(name="run_max_agent_loop_background")
def run_max_agent_loop_background_task(
    *,
    agent_id: str,
    user_id: str,
    user_text: str,
    chat_id: int,
    author: str = "",
    vision_context: str = "",
) -> None:
    asyncio.run(
        _run_max_agent_loop_background_async(
            agent_id=agent_id,
            user_id=user_id,
            user_text=user_text,
            chat_id=chat_id,
            author=author,
            vision_context=vision_context,
        )
    )


async def _run_max_agent_loop_background_async(
    *,
    agent_id: str,
    user_id: str,
    user_text: str,
    chat_id: int,
    author: str = "",
    vision_context: str = "",
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    bot = MaxBotService()
    try:
        async with session_factory() as db:
            agent = await db.get(AgentInstance, UUID(agent_id))
            user = await db.get(User, UUID(user_id))
            if not agent or not user:
                logger.warning("Background agent loop: agent or user not found")
                return
            result = await run_max_interactive_loop(
                db,
                redis_client,
                user,
                agent,
                user_text=user_text,
                chat_id=chat_id,
                author=author,
                vision_context=vision_context,
                bot=bot,
            )
            await deliver_runtime_result(bot, chat_id=chat_id, result=result)
            await db.commit()
    except Exception:
        logger.exception("run_max_agent_loop_background failed agent=%s", agent_id)
        try:
            await bot.send_message(
                None,
                "Не удалось завершить задачу. Попробуйте ещё раз или уточните запрос.",
                chat_id=chat_id,
            )
        except Exception:
            logger.exception("Background agent loop error notify failed chat=%s", chat_id)
        raise
    finally:
        await redis_client.aclose()
        await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Плановый постинг (агент «Постинг»)
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(name="dispatch_poster_scheduled")
def dispatch_poster_scheduled_task() -> None:
    asyncio.run(_dispatch_poster_scheduled_async())


async def _dispatch_poster_scheduled_async() -> None:
    """Проверяет расписание всех активных poster-агентов и генерирует посты по времени."""
    from datetime import datetime, timezone as _tz, timedelta

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    _WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    try:
        from sqlalchemy import select
        from app.models.agent import AgentStatus

        async with session_factory() as db:
            # Include ACTIVE and DRAFT poster agents (poster agents start as draft
            # until first verify-channel; also catches agents created before this fix)
            # Only process ACTIVE agents — DRAFT agents haven't passed verify-channel
            result = await db.execute(
                select(AgentInstance).where(
                    AgentInstance.status == AgentStatus.ACTIVE.value
                )
            )
            agents = result.scalars().all()

            now = datetime.now(_tz.utc)

            bot = MaxBotService()

            for agent in agents:
                cfg = dict(agent.config or {})
                if cfg.get("task_mode") != "poster" and cfg.get("template") != "poster":
                    continue
                # Skip if explicitly disabled by user toggle
                if cfg.get("poster_enabled") is False:
                    continue

                from app.services.agent.poster_executor import get_poster_schedule
                schedule = get_poster_schedule(agent)
                if not schedule:
                    continue  # ручной режим — не запускаем автоматически

                # Localize to agent's configured timezone
                tz_name = cfg.get("poster_timezone", "Europe/Moscow")
                try:
                    import zoneinfo
                    tz = zoneinfo.ZoneInfo(tz_name)
                    now_local = now.astimezone(tz)
                except Exception:
                    now_local = now.astimezone()

                current_day = _WEEKDAY_KEYS[now_local.weekday()]

                # Проверяем каждый слот расписания
                for slot in schedule:
                    slot_day = slot.get("day", "")
                    slot_time = slot.get("time", "")
                    if slot_day != current_day:
                        continue
                    if not slot_time:
                        continue

                    # Проверяем время (±5 минут)
                    try:
                        sh, sm = map(int, slot_time.split(":"))
                    except ValueError:
                        continue
                    target = now_local.replace(hour=sh, minute=sm, second=0, microsecond=0)
                    if abs((now_local - target).total_seconds()) > 300:
                        continue

                    # Atomic dedup: SET NX prevents two workers from racing.
                    dedup_key = f"poster_dispatched:{agent.id}:{current_day}:{slot_time}"
                    acquired = await redis_client.set(dedup_key, "1", nx=True, ex=3600)
                    if not acquired:
                        continue  # another worker already claimed this slot

                    # Генерируем пост для этого слота
                    try:
                        from app.services.agent.poster_executor import (
                            generate_post,
                            generate_poster_image,
                            get_approval_mode,
                            get_poster_channel_id,
                            publish_to_channel,
                            save_pending_draft,
                            save_post_to_history,
                            send_draft_for_approval,
                            update_post_status,
                            mark_draft_message_done,
                            _pick_next_topic,
                        )
                        from app.services.providers.factory import resolve_agent_providers
                        from app.core.limiter import RateLimiter
                        import uuid as _uuid

                        # Billing: scheduled post counts as 1 request for the agent owner
                        from sqlalchemy import select as _select
                        _user_res = await db.execute(_select(User).where(User.id == agent.user_id))
                        _owner = _user_res.scalar_one_or_none()
                        if _owner:
                            _limiter = RateLimiter(redis_client)
                            _allowed, _used, _limit = await _limiter.check_search_limit(
                                str(_owner.id), _owner.plan, user=_owner
                            )
                            if not _allowed:
                                logger.info(
                                    "Poster scheduled: agent=%s skipped — daily limit reached (used=%s, limit=%s)",
                                    agent.id, _used, _limit,
                                )
                                continue

                        topic = _pick_next_topic(agent)
                        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
                        post_text = await generate_post(agent, topic, llm)
                        post_id = str(_uuid.uuid4())

                        save_post_to_history(agent, post_id=post_id, topic=topic, text=post_text, status="draft")

                        approval_mode = get_approval_mode(agent)
                        channel_id = get_poster_channel_id(agent)

                        # Generate image if configured
                        image_bytes = await generate_poster_image(
                            agent, topic, post_text, db=db, redis_client=redis_client
                        )

                        # If AI image was expected but not generated (limit or error),
                        # add a note to DM draft so user knows to add image manually
                        cfg_a = dict(agent.config or {})
                        wants_ai_image = str(cfg_a.get("poster_media") or "none").lower() == "ai"
                        image_failed = wants_ai_image and image_bytes is None

                        # Append note to DM text when image was not generated
                        dm_text = post_text
                        if image_failed and approval_mode != "auto":
                            dm_text = post_text + "\n\n_⚠️ ИИ-картинка не сгенерирована (исчерпан лимит или ошибка). Загрузите фото вручную в треде агента._"

                        if approval_mode == "auto" and channel_id:
                            ok = await publish_to_channel(bot, channel_id=channel_id, text=post_text, image_bytes=image_bytes)
                            if ok:
                                update_post_status(agent, post_id, "published")
                        else:
                            # Manual: send draft with image to DM or group
                            save_pending_draft(agent, post_id=post_id, topic=topic, text=dm_text)
                            msg_id = await send_draft_for_approval(
                                agent, db, bot,
                                post_id=post_id, topic=topic, text=dm_text,
                                image_bytes=image_bytes,
                            )
                            if msg_id:
                                save_pending_draft(agent, post_id=post_id, topic=topic,
                                                   text=post_text, draft_message_id=msg_id)

                        # DO NOT reassign agent.config = cfg here — save_pending_draft /
                        # _save_cfg already updated agent.config with the pending draft.
                        # Reassigning would erase the draft and break DM callback buttons.
                        from sqlalchemy.orm.attributes import flag_modified as _fm_task
                        _fm_task(agent, "config")
                        await db.commit()
                        logger.info(
                            "Poster scheduled: agent=%s slot=%s/%s topic=%s mode=%s",
                            agent.id, slot_day, slot_time, topic, approval_mode,
                        )

                    except Exception as exc:
                        logger.exception("Poster slot failed agent=%s slot=%s/%s: %s",
                                         agent.id, slot_day, slot_time, exc)

    finally:
        await redis_client.aclose()
        await engine.dispose()
