"""TTL, очистка просроченных файлов, reconcile сирот на диске, heartbeat для мониторинга."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.attachments import UPLOAD_TTL_HOURS
from app.constants.image_gen import GENERATED_IMAGE_TTL_HOURS
from app.core.config import Settings, get_settings
from app.models.message import Message
from app.models.thread import Thread
from app.models.uploaded_file import UploadedFile
from app.services.app_settings import get_setting
from app.services.upload_storage import _root, delete_upload_file

logger = logging.getLogger(__name__)

CLEANUP_HEARTBEAT_KEY = "maintenance:cleanup_expired_uploads:last_run"
CLEANUP_COUNT_KEY = "maintenance:cleanup_expired_uploads:last_count"
RECONCILE_HEARTBEAT_KEY = "maintenance:reconcile_orphan_uploads:last_run"
RECONCILE_COUNT_KEY = "maintenance:reconcile_orphan_uploads:last_count"

# Расписание cleanup каждые 6 ч — предупреждение, если heartbeat старше 9 ч.
CLEANUP_STALE_AFTER_SECONDS = 9 * 3600
RECONCILE_STALE_AFTER_SECONDS = 8 * 24 * 3600


def is_file_expired(row: UploadedFile, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return bool(row.expires_at and row.expires_at < now)


async def resolve_upload_ttl_hours(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    raw = int(await get_setting("upload_ttl_hours", db, redis_client, settings))
    return max(1, min(raw, 24 * 7))


async def resolve_generated_image_ttl_hours(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    raw = int(await get_setting("generated_image_ttl_hours", db, redis_client, settings))
    return max(1, min(raw, 24 * 30))


async def resolve_max_upload_mb_free(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    raw = int(await get_setting("max_upload_mb_free", db, redis_client, settings))
    return max(1, min(raw, 100))


async def resolve_max_upload_mb_pro(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    raw = int(await get_setting("max_upload_mb_pro", db, redis_client, settings))
    return max(1, min(raw, 500))


def default_upload_ttl_hours(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    return max(1, getattr(settings, "upload_ttl_hours", UPLOAD_TTL_HOURS))


def default_generated_image_ttl_hours(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    return max(1, getattr(settings, "generated_image_ttl_hours", GENERATED_IMAGE_TTL_HOURS))


async def purge_uploaded_file_row(db: AsyncSession, row: UploadedFile) -> None:
    delete_upload_file(row.storage_key)
    await db.delete(row)


async def cleanup_expired_uploads(
    db: AsyncSession,
    *,
    user_id: UUID | None = None,
    batch_limit: int | None = None,
) -> int:
    """Удалить просроченные uploaded_files (диск + БД)."""
    now = datetime.now(timezone.utc)
    query = select(UploadedFile).where(
        UploadedFile.expires_at.isnot(None),
        UploadedFile.expires_at < now,
    )
    if user_id is not None:
        query = query.where(UploadedFile.user_id == user_id)
    if batch_limit is not None:
        query = query.limit(batch_limit)

    result = await db.execute(query)
    rows = list(result.scalars().all())
    for row in rows:
        delete_upload_file(row.storage_key)

    if not rows:
        return 0

    ids = [row.id for row in rows]
    await db.execute(delete(UploadedFile).where(UploadedFile.id.in_(ids)))
    return len(rows)


async def purge_expired_file_if_needed(db: AsyncSession, row: UploadedFile) -> bool:
    """При доступе к просроченному файлу — сразу удалить с диска и из БД."""
    if not is_file_expired(row):
        return False
    await purge_uploaded_file_row(db, row)
    await db.flush()
    return True


def _attachment_file_ids(raw: list | dict | None) -> set[UUID]:
    if not raw:
        return set()
    items = raw if isinstance(raw, list) else []
    out: set[UUID] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "") == "markdown_document":
            continue
        raw_id = item.get("id")
        if not raw_id:
            continue
        try:
            out.add(UUID(str(raw_id)))
        except ValueError:
            continue
    return out


async def collect_referenced_file_ids_for_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    exclude_thread_ids: set[UUID] | None = None,
) -> set[UUID]:
    exclude_thread_ids = exclude_thread_ids or set()
    result = await db.execute(
        select(Message.thread_id, Message.attachments)
        .join(Thread, Message.thread_id == Thread.id)
        .where(
            Thread.user_id == user_id,
            Thread.deleted_at.is_(None),
            Message.attachments.isnot(None),
        )
    )
    referenced: set[UUID] = set()
    for thread_id, attachments in result.all():
        if thread_id in exclude_thread_ids:
            continue
        referenced |= _attachment_file_ids(attachments)
    return referenced


async def purge_generated_files_exclusive_to_threads(
    db: AsyncSession,
    user_id: UUID,
    thread_ids: set[UUID],
) -> int:
    """
    Удалить generated_doc / generated файлы, на которые ссылаются только удаляемые треды.
    Вложения поиска (image/document) не трогаем — они привязаны к user_id, не к треду.
    """
    if not thread_ids:
        return 0

    candidate_ids: set[UUID] = set()
    msg_result = await db.execute(
        select(Message.attachments).where(Message.thread_id.in_(thread_ids))
    )
    for (attachments,) in msg_result.all():
        candidate_ids |= _attachment_file_ids(attachments)

    if not candidate_ids:
        return 0

    still_referenced = await collect_referenced_file_ids_for_user(
        db,
        user_id,
        exclude_thread_ids=thread_ids,
    )
    to_delete = candidate_ids - still_referenced
    if not to_delete:
        return 0

    files_result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(to_delete),
            UploadedFile.user_id == user_id,
            UploadedFile.media_kind.in_(("generated_doc", "generated")),
        )
    )
    rows = list(files_result.scalars().all())
    for row in rows:
        await purge_uploaded_file_row(db, row)
    return len(rows)


async def reconcile_orphan_disk_files(db: AsyncSession, *, max_files: int = 5000) -> int:
    """Удалить файлы на диске без записи в uploaded_files.storage_key."""
    result = await db.execute(
        select(UploadedFile.storage_key).where(UploadedFile.storage_key.isnot(None))
    )
    known = {row[0] for row in result.all() if row[0]}

    root = _root()
    removed = 0
    if not root.is_dir():
        return 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel in known:
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            logger.exception("failed to remove orphan upload file %s", rel)
        if removed >= max_files:
            break

    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    return removed


async def count_expired_pending(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(func.count())
        .select_from(UploadedFile)
        .where(
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at < now,
        )
    )
    return int(result.scalar_one() or 0)


def _disk_usage_sample() -> dict[str, int]:
    root = _root()
    if not root.is_dir():
        return {"files_on_disk": 0, "bytes_on_disk": 0}
    files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_file():
            files += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass
        if files >= 10000:
            break
    return {"files_on_disk": files, "bytes_on_disk": total_bytes, "scan_capped": files >= 10000}


async def storage_stats(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    total_rows = await db.execute(select(func.count()).select_from(UploadedFile))
    with_storage = await db.execute(
        select(func.count())
        .select_from(UploadedFile)
        .where(UploadedFile.storage_key.isnot(None))
    )
    expired_pending = await count_expired_pending(db)
    return {
        "uploaded_files_rows": int(total_rows.scalar_one() or 0),
        "rows_with_storage_key": int(with_storage.scalar_one() or 0),
        "expired_pending_cleanup": expired_pending,
        **_disk_usage_sample(),
    }


async def record_maintenance_run(
    redis_client: redis.Redis,
    *,
    heartbeat_key: str,
    count_key: str,
    removed: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        await redis_client.set(heartbeat_key, now)
        await redis_client.set(count_key, str(removed))
    except Exception:
        logger.debug("maintenance heartbeat write failed", exc_info=True)


async def maintenance_health(redis_client: redis.Redis) -> dict:
    now = datetime.now(timezone.utc)

    async def _entry(heartbeat_key: str, count_key: str, stale_after: int) -> dict:
        try:
            last_run_raw = await redis_client.get(heartbeat_key)
            count_raw = await redis_client.get(count_key)
        except Exception:
            return {"last_run": None, "last_count": None, "stale": True, "error": "redis_unavailable"}

        last_run = None
        stale = True
        if last_run_raw:
            try:
                last_run = datetime.fromisoformat(str(last_run_raw).replace("Z", "+00:00"))
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                stale = (now - last_run).total_seconds() > stale_after
            except ValueError:
                stale = True

        return {
            "last_run": last_run.isoformat() if last_run else None,
            "last_count": int(count_raw) if count_raw is not None else None,
            "stale": stale,
        }

    cleanup = await _entry(CLEANUP_HEARTBEAT_KEY, CLEANUP_COUNT_KEY, CLEANUP_STALE_AFTER_SECONDS)
    reconcile = await _entry(RECONCILE_HEARTBEAT_KEY, RECONCILE_COUNT_KEY, RECONCILE_STALE_AFTER_SECONDS)
    return {
        "cleanup_expired_uploads": cleanup,
        "reconcile_orphan_uploads": reconcile,
        "healthy": not cleanup.get("stale") and not reconcile.get("stale"),
    }
