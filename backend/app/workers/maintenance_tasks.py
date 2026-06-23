import asyncio
import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.account_purge import purge_expired_deleted_accounts
from app.services.upload_lifecycle import (
    CLEANUP_COUNT_KEY,
    CLEANUP_HEARTBEAT_KEY,
    RECONCILE_COUNT_KEY,
    RECONCILE_HEARTBEAT_KEY,
    cleanup_expired_uploads,
    reconcile_orphan_disk_files,
    record_maintenance_run,
)
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="cleanup_expired_uploads")
def cleanup_expired_uploads_task() -> None:
    asyncio.run(_cleanup_expired_uploads_async())


async def _cleanup_expired_uploads_async() -> int:
    settings_module = __import__("app.core.config", fromlist=["get_settings"])
    settings = settings_module.get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    deleted = 0

    try:
        async with session_factory() as db:
            deleted = await cleanup_expired_uploads(db)
            await db.commit()
        await record_maintenance_run(
            redis_client,
            heartbeat_key=CLEANUP_HEARTBEAT_KEY,
            count_key=CLEANUP_COUNT_KEY,
            removed=deleted,
        )
    finally:
        await redis_client.aclose()
        await engine.dispose()

    logger.info("cleanup_expired_uploads: removed %s rows", deleted)
    return deleted


@celery.task(name="reconcile_orphan_uploads")
def reconcile_orphan_uploads_task() -> None:
    asyncio.run(_reconcile_orphan_uploads_async())


async def _reconcile_orphan_uploads_async() -> int:
    settings_module = __import__("app.core.config", fromlist=["get_settings"])
    settings = settings_module.get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    removed = 0

    try:
        async with session_factory() as db:
            removed = await reconcile_orphan_disk_files(db)
            await db.commit()
        await record_maintenance_run(
            redis_client,
            heartbeat_key=RECONCILE_HEARTBEAT_KEY,
            count_key=RECONCILE_COUNT_KEY,
            removed=removed,
        )
    finally:
        await redis_client.aclose()
        await engine.dispose()

    logger.info("reconcile_orphan_uploads: removed %s orphan files", removed)
    return removed


@celery.task(name="publish_scheduled_blog_posts")
def publish_scheduled_blog_posts_task() -> None:
    asyncio.run(_publish_scheduled_blog_posts_async())


async def _publish_scheduled_blog_posts_async() -> int:
    """Публикует статьи с status='scheduled' у которых publish_at <= now()."""
    from datetime import datetime, timezone
    settings_module = __import__("app.core.config", fromlist=["get_settings"])
    settings = settings_module.get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    published = 0

    try:
        now = datetime.now(timezone.utc)
        from sqlalchemy import select, update
        from app.models.blog import BlogPost

        async with session_factory() as db:
            result = await db.execute(
                select(BlogPost).where(
                    BlogPost.status == "scheduled",
                    BlogPost.publish_at.is_not(None),
                    BlogPost.publish_at <= now,
                )
            )
            posts = list(result.scalars().all())
            for post in posts:
                post.status = "published"
                if not post.published_at:
                    post.published_at = post.publish_at or now
                post.robots_index = True
                published += 1
            if posts:
                await db.commit()
                # Rebuild prerender for published posts
                try:
                    from app.services.blog_prerender import rebuild_all_prerender
                    await rebuild_all_prerender(db)
                except Exception:
                    logger.warning("blog prerender failed after scheduled publish", exc_info=True)
    finally:
        await engine.dispose()

    if published:
        logger.info("publish_scheduled_blog_posts: published %s posts", published)
    return published


@celery.task(name="purge_deleted_accounts")
def purge_deleted_accounts_task() -> None:
    asyncio.run(_purge_deleted_accounts_async())


async def _purge_deleted_accounts_async() -> int:
    settings_module = __import__("app.core.config", fromlist=["get_settings"])
    settings = settings_module.get_settings()
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
