import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.uploaded_file import UploadedFile
from app.services.upload_storage import delete_upload_file
from celery_app import celery

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
