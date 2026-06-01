from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.admin_user import AdminUser
from app.models.broadcast import Broadcast, BroadcastAudience, BroadcastLog, BroadcastStatus
from app.models.user import Plan, User
from app.schemas.admin import (
    AudiencePreview,
    BotWelcomeMediaOut,
    BotWelcomeOut,
    BotWelcomeUpdate,
    BroadcastCreate,
    BroadcastLogOut,
    BroadcastOut,
)
from app.services.admin_audit import log_admin_action
from app.services.app_settings import get_setting, set_setting
from app.services.bot import MaxBotService
from app.workers.broadcast_tasks import send_broadcast_task

router = APIRouter(prefix="/broadcasts", tags=["admin-broadcasts"])

WELCOME_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
WELCOME_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
MAX_WELCOME_BYTES = 50 * 1024 * 1024


async def _audience_count(db: AsyncSession, audience: BroadcastAudience) -> int:
    q = select(func.count()).select_from(User).where(
        User.deleted_at.is_(None),
        User.max_user_id.isnot(None),
    )
    if audience == BroadcastAudience.FREE:
        q = q.where(User.plan == Plan.FREE)
    elif audience == BroadcastAudience.PRO:
        q = q.where(User.plan == Plan.PRO)
    return int(await db.scalar(q) or 0)


async def _load_welcome(db: AsyncSession) -> BotWelcomeOut:
    redis = await get_redis()
    settings = get_settings()
    text = str(await get_setting("bot_welcome_text", db, redis))
    media_type = str(await get_setting("bot_welcome_media_type", db, redis) or "none")
    media_token = str(await get_setting("bot_welcome_media_token", db, redis) or "").strip() or None
    media_filename = str(await get_setting("bot_welcome_media_filename", db, redis) or "").strip() or None
    webhook_url = f"{settings.api_public_url.rstrip('/')}/api/bot/webhook"
    return BotWelcomeOut(
        text=text,
        media_type=media_type if media_type in {"none", "image", "video"} else "none",
        media_token=media_token,
        media_filename=media_filename,
        webhook_url=webhook_url,
    )


@router.get("/welcome", response_model=BotWelcomeOut)
async def get_bot_welcome(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("broadcasts:read")),
):
    return await _load_welcome(db)


@router.put("/welcome", response_model=BotWelcomeOut)
async def update_bot_welcome(
    body: BotWelcomeUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    redis = await get_redis()
    if body.media_type == "none":
        media_token = ""
        media_filename = ""
    else:
        media_token = (body.media_token or "").strip()
        media_filename = (body.media_filename or "").strip()
        if not media_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Загрузите изображение или видео перед сохранением",
            )

    await set_setting("bot_welcome_text", body.text.strip(), db, redis, admin.id)
    await set_setting("bot_welcome_media_type", body.media_type, db, redis, admin.id)
    await set_setting("bot_welcome_media_token", media_token, db, redis, admin.id)
    await set_setting("bot_welcome_media_filename", media_filename, db, redis, admin.id)

    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.welcome.update",
        resource_type="settings",
        details={
            "text_len": len(body.text.strip()),
            "media_type": body.media_type,
            "has_media": bool(media_token),
        },
        ip_address=request.client.host if request.client else None,
    )
    return await _load_welcome(db)


@router.post("/welcome/media", response_model=BotWelcomeMediaOut)
async def upload_bot_welcome_media(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
    file: UploadFile = File(...),
):
    filename = (file.filename or "media").lower()
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext in WELCOME_IMAGE_EXT:
        media_type = "image"
    elif ext in WELCOME_VIDEO_EXT:
        media_type = "video"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются изображения (jpg, png, webp, gif) и видео (mp4, mov, webm)",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")
    if len(data) > MAX_WELCOME_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл больше 50 МБ")

    bot = MaxBotService()
    token = await bot.upload_media(data, filename, media_type)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось загрузить файл в MAX. Проверьте BOT_TOKEN.",
        )

    redis = await get_redis()
    await set_setting("bot_welcome_media_type", media_type, db, redis, admin.id)
    await set_setting("bot_welcome_media_token", token, db, redis, admin.id)
    await set_setting("bot_welcome_media_filename", file.filename or filename, db, redis, admin.id)

    return BotWelcomeMediaOut(media_type=media_type, media_token=token, media_filename=file.filename or filename)


@router.delete("/welcome/media")
async def clear_bot_welcome_media(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    redis = await get_redis()
    await set_setting("bot_welcome_media_type", "none", db, redis, admin.id)
    await set_setting("bot_welcome_media_token", "", db, redis, admin.id)
    await set_setting("bot_welcome_media_filename", "", db, redis, admin.id)
    return {"ok": True}


@router.get("/audience-preview", response_model=AudiencePreview)
async def audience_preview(
    db: Annotated[AsyncSession, Depends(get_db)],
    audience: BroadcastAudience = Query(default=BroadcastAudience.ALL),
    _admin=Depends(require_permission("broadcasts:read")),
):
    count = await _audience_count(db, audience)
    return AudiencePreview(audience=audience, recipient_count=count)


@router.get("", response_model=list[BroadcastOut])
async def list_broadcasts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("broadcasts:read")),
):
    result = await db.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(50))
    return result.scalars().all()


@router.post("", response_model=BroadcastOut)
async def create_broadcast(
    body: BroadcastCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    broadcast = Broadcast(text=body.text, audience=body.audience, status=BroadcastStatus.DRAFT)
    db.add(broadcast)
    await db.flush()
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.create",
        resource_type="broadcast",
        resource_id=str(broadcast.id),
        details={"audience": body.audience.value, "text_len": len(body.text)},
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return broadcast


@router.get("/{broadcast_id}/logs", response_model=list[BroadcastLogOut])
async def broadcast_logs(
    broadcast_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("broadcasts:read")),
):
    result = await db.execute(
        select(BroadcastLog)
        .where(BroadcastLog.broadcast_id == broadcast_id)
        .order_by(BroadcastLog.created_at.desc())
        .limit(200)
    )
    return result.scalars().all()


@router.post("/{broadcast_id}/send")
async def send_broadcast(
    broadcast_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    redis = await get_redis()
    rate_key = "admin:broadcast:hourly"
    sent_hourly = await redis.incr(rate_key)
    if sent_hourly == 1:
        await redis.expire(rate_key, 3600)
    if sent_hourly > 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Broadcast rate limit")

    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")
    if broadcast.status == BroadcastStatus.SENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already sending")

    broadcast.status = BroadcastStatus.SENDING
    send_broadcast_task.delay(str(broadcast_id))
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.send",
        resource_type="broadcast",
        resource_id=str(broadcast_id),
        details={"audience": broadcast.audience.value},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "broadcast_id": str(broadcast_id)}
