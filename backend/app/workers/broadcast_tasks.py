import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.broadcast import Broadcast, BroadcastAudience, BroadcastLog, BroadcastLogStatus, BroadcastStatus
from app.models.user import Plan, User
from app.services.bot import MaxBotService
from app.services.bot_media import max_bot_media_attachments
from celery_app import celery

BATCH_SIZE = 50
SEND_DELAY_SEC = 0.12  # ~8 msg/s — безопаснее лимита MAX (~30 rps)


@celery.task(name="send_broadcast")
def send_broadcast_task(broadcast_id: str) -> None:
    asyncio.run(_send_broadcast_async(broadcast_id))


async def _send_broadcast_async(broadcast_id: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    bot = MaxBotService()

    async with session_factory() as db:
        result = await db.execute(select(Broadcast).where(Broadcast.id == uuid.UUID(broadcast_id)))
        broadcast = result.scalar_one_or_none()
        if not broadcast:
            return

        q = select(User).where(User.deleted_at.is_(None), User.max_user_id.isnot(None))
        if broadcast.audience == BroadcastAudience.FREE:
            q = q.where(User.plan == Plan.FREE)
        elif broadcast.audience == BroadcastAudience.PRO:
            q = q.where(User.plan == Plan.PRO)

        users_result = await db.execute(q)
        users = users_result.scalars().all()

        attachments = max_bot_media_attachments(broadcast.media_type, broadcast.media_token)
        message_text = broadcast.text.strip() or " "

        sent = 0
        failed = 0
        for user in users:
            result = await bot.send_message(user.max_user_id, message_text, attachments)
            if not result.ok and result.retry_after_sec:
                await asyncio.sleep(result.retry_after_sec)
                result = await bot.send_message(user.max_user_id, message_text, attachments)

            log = BroadcastLog(
                broadcast_id=broadcast.id,
                user_id=user.id,
                status=BroadcastLogStatus.SENT if result.ok else BroadcastLogStatus.FAILED,
                error=None if result.ok else (result.error or "send failed"),
            )
            db.add(log)
            if result.ok:
                sent += 1
            else:
                failed += 1

            if (sent + failed) % BATCH_SIZE == 0:
                await db.commit()

            await asyncio.sleep(SEND_DELAY_SEC)

        broadcast.sent_count = sent
        broadcast.failed_count = failed
        if sent == 0 and failed > 0:
            broadcast.status = BroadcastStatus.FAILED
        else:
            broadcast.status = BroadcastStatus.DONE
        await db.commit()

    await engine.dispose()
