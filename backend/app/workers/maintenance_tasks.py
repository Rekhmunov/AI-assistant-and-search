import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.uploaded_file import UploadedFile
from app.services.account_purge import purge_expired_deleted_accounts
from app.services.upload_storage import delete_upload_file
from celery_app import celery

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@celery.task(name="cleanup_expired_uploads")
def cleanup_expired_uploads_task() -> None:
    asyncio.run(_cleanup_expired_uploads_async())


async def _cleanup_expired_uploads_async() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    deleted = 0

    async with session_factory() as db:
        expired = await db.execute(
            select(UploadedFile).where(
                UploadedFile.expires_at.isnot(None),
                UploadedFile.expires_at < now,
            )
        )
        for row in expired.scalars().all():
            delete_upload_file(row.storage_key)
        result = await db.execute(
            delete(UploadedFile).where(
                UploadedFile.expires_at.isnot(None),
                UploadedFile.expires_at < now,
            )
        )
        deleted = result.rowcount or 0
        await db.commit()

    await engine.dispose()
    logger.info("cleanup_expired_uploads: removed %s rows", deleted)
    return deleted


@celery.task(name="purge_deleted_accounts")
def purge_deleted_accounts_task() -> None:
    asyncio.run(_purge_deleted_accounts_async())


async def _purge_deleted_accounts_async() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    purged = 0

    try:
        async with session_factory() as db:
            purged = await purge_expired_deleted_accounts(
                db,
                redis_client,
                retention_days=settings.deleted_account_retention_days,
            )
    finally:
        await redis_client.aclose()
        await engine.dispose()

    logger.info("purge_deleted_accounts: removed %s users", purged)
    return purged
