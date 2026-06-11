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
