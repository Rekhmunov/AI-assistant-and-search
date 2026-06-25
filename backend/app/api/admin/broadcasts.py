from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
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
from app.services.bot_media import read_and_upload_max_media
from app.workers.broadcast_tasks import send_broadcast_task

router = APIRouter(prefix="/broadcasts", tags=["admin-broadcasts"])


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
    media_type, token, filename = await read_and_upload_max_media(file)

    redis = await get_redis()
    await set_setting("bot_welcome_media_type", media_type, db, redis, admin.id)
    await set_setting("bot_welcome_media_token", token, db, redis, admin.id)
    await set_setting("bot_welcome_media_filename", filename, db, redis, admin.id)

    return BotWelcomeMediaOut(media_type=media_type, media_token=token, media_filename=filename)


@router.post("/media", response_model=BotWelcomeMediaOut)
async def upload_broadcast_media(
    _admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
    file: UploadFile = File(...),
):
    """Загрузить фото/видео в MAX для черновика рассылки (токен подставляется при создании)."""
    media_type, token, filename = await read_and_upload_max_media(file)
    return BotWelcomeMediaOut(media_type=media_type, media_token=token, media_filename=filename)


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
    media_type = body.media_type if body.media_type in {"none", "image", "video"} else "none"
    media_token = (body.media_token or "").strip() or None
    media_filename = (body.media_filename or "").strip() or None
    if media_type == "none":
        media_token = None
        media_filename = None

    broadcast = Broadcast(
        text=body.text.strip(),
        audience=body.audience,
        status=BroadcastStatus.DRAFT,
        media_type=media_type,
        media_token=media_token,
        media_filename=media_filename,
    )
    db.add(broadcast)
    await db.flush()
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.create",
        resource_type="broadcast",
        resource_id=str(broadcast.id),
        details={
            "audience": body.audience.value,
            "text_len": len(body.text.strip()),
            "media_type": media_type,
            "has_media": bool(media_token),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return broadcast


@router.delete("")
async def clear_broadcast_history(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    """Удалить все рассылки, кроме идущих отправки (status=sending)."""
    sending_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Broadcast)
            .where(Broadcast.status == BroadcastStatus.SENDING)
        )
        or 0
    )
    if sending_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя очистить историю: есть рассылка в статусе «отправка». Дождитесь завершения.",
        )

    result = await db.execute(delete(Broadcast))
    deleted = result.rowcount or 0
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.clear_history",
        resource_type="broadcast",
        details={"deleted": deleted},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "deleted": deleted}


@router.delete("/{broadcast_id}")
async def delete_broadcast(
    broadcast_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рассылка не найдена")
    if broadcast.status == BroadcastStatus.SENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя удалить рассылку во время отправки",
        )

    await db.delete(broadcast)
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.delete",
        resource_type="broadcast",
        resource_id=str(broadcast_id),
        details={"audience": broadcast.audience.value, "status": broadcast.status.value},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "deleted": 1}


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
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Рассылка запускалась недавно — подождите несколько минут")

    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рассылка не найдена")
    if broadcast.status == BroadcastStatus.SENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Рассылка уже выполняется")

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


# ─── Direct / personal message ────────────────────────────────────────────────

@router.get("/user-search")
async def search_users_for_dm(
    q: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    """Поиск пользователей по email или MAX ID для личного сообщения."""
    from sqlalchemy import or_

    q = q.strip()
    conditions = [User.deleted_at.is_(None)]

    # If q looks like a number — search by max_user_id
    if q.lstrip("-").isdigit():
        try:
            max_id = int(q)
            conditions.append(User.max_user_id == max_id)
        except ValueError:
            pass
    else:
        # Email or name partial match
        conditions.append(
            or_(
                User.email.ilike(f"%{q}%"),
                User.name.ilike(f"%{q}%"),
            )
        )

    result = await db.execute(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc())
        .limit(10)
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email or "",
            "name": u.name or "",
            "plan": u.plan.value if u.plan else "free",
            "max_user_id": u.max_user_id,
            "has_max": u.max_user_id is not None,
        }
        for u in users
    ]


class DirectMessageIn(BaseModel):
    user_id: str
    text: str
    media_type: str = "none"
    media_token: str | None = None
    media_filename: str | None = None


class DirectMessageOut(BaseModel):
    ok: bool
    error: str | None = None
    max_user_id: int | None = None


@router.post("/direct", response_model=DirectMessageOut)
async def send_direct_message(
    body: DirectMessageIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    """Отправить личное сообщение конкретному пользователю через MAX бот."""
    import uuid as _uuid

    try:
        uid = _uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный user_id")

    result = await db.execute(select(User).where(User.id == uid, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if not user.max_user_id:
        raise HTTPException(status_code=422, detail="У пользователя нет MAX ID — он не запускал бота")

    from app.services.bot import MaxBotService
    from app.services.bot_media import max_bot_media_attachments

    bot = MaxBotService()
    attachments = max_bot_media_attachments(body.media_type, body.media_token)
    message_text = body.text.strip() or " "

    send_result = await bot.send_message(user.max_user_id, message_text, attachments)

    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.direct",
        resource_type="user",
        resource_id=str(uid),
        details={
            "max_user_id": user.max_user_id,
            "text_len": len(message_text),
            "ok": send_result.ok,
            "error": send_result.error or None,
        },
        ip_address=request.client.host if request.client else None,
    )

    return DirectMessageOut(
        ok=send_result.ok,
        error=send_result.error if not send_result.ok else None,
        max_user_id=user.max_user_id,
    )
