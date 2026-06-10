"""Celery: отправка напоминаний агентов в MAX."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services.agent.dispatch import dispatch_due_reminders
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="dispatch_agent_reminders")
def dispatch_agent_reminders_task() -> None:
    asyncio.run(_dispatch_agent_reminders_async())


async def _dispatch_agent_reminders_async() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        count = await dispatch_due_reminders(db)
        await db.commit()
        if count:
            logger.info("Celery dispatched %s agent reminders", count)

    await engine.dispose()
