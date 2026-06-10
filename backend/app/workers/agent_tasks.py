"""Celery: отправка напоминаний агентов в MAX."""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services.agent.activity_log import purge_old_agent_activity_logs
from app.services.agent.dispatch import dispatch_due_reminders
from app.services.agent.reminders import get_due_reminders
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
