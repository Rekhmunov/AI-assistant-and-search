"""Окончательное удаление аккаунтов после срока хранения (soft-delete → purge)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.refresh_tokens import revoke_refresh_tokens
from app.services.upload_storage import delete_upload_file

logger = logging.getLogger(__name__)


async def purge_user_account(db: AsyncSession, redis_client: redis.Redis, user: User) -> None:
    """Удалить пользователя и связанные данные (CASCADE), включая файлы на диске."""
    files = await db.execute(select(UploadedFile).where(UploadedFile.user_id == user.id))
    for row in files.scalars().all():
        delete_upload_file(row.storage_key)

    await revoke_refresh_tokens(redis_client, str(user.id))
    await db.delete(user)
    logger.info("purged deleted user id=%s deleted_at=%s", user.id, user.deleted_at)


async def purge_expired_deleted_accounts(
    db: AsyncSession,
    redis_client: redis.Redis,
    *,
    retention_days: int,
) -> int:
    """Удалить аккаунты с deleted_at старше retention_days. Возвращает число удалённых."""
    if retention_days < 1:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        select(User).where(
            User.deleted_at.isnot(None),
            User.deleted_at < cutoff,
        )
    )
    users = list(result.scalars().all())
    for user in users:
        await purge_user_account(db, redis_client, user)

    if users:
        await db.commit()

    return len(users)
