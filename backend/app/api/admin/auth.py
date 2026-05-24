from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as redis

from app.api.deps import get_current_admin, get_db, get_redis
from app.core.config import get_settings
from app.core.security import create_admin_token, verify_password
from app.models.admin_user import AdminUser
from app.schemas.admin import AdminLoginRequest, AdminUserOut
from app.services.admin_audit import log_admin_action

router = APIRouter(prefix="/auth", tags=["admin-auth"])


@router.post("/login")
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    settings = get_settings()

    rate_key = f"admin_login_attempts:{body.email.lower()}"
    attempts = await redis_client.incr(rate_key)
    if attempts == 1:
        await redis_client.expire(rate_key, 900)
    if attempts > 10:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")

    result = await db.execute(select(AdminUser).where(AdminUser.email == body.email.lower()))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    admin.last_login_at = datetime.now(timezone.utc)
    token = create_admin_token(str(admin.id), settings)
    await log_admin_action(
        db,
        admin=admin,
        action="admin.login",
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await redis_client.delete(rate_key)

    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="none" if not settings.debug else "lax",
        max_age=settings.admin_session_expire_hours * 3600,
        path="/",
    )
    return {"ok": True, "admin": AdminUserOut.model_validate(admin)}


@router.post("/logout")
async def admin_logout(
    response: Response,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
):
    await log_admin_action(
        db,
        admin=admin,
        action="admin.logout",
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    response.delete_cookie("admin_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=AdminUserOut)
async def admin_me(admin: Annotated[AdminUser, Depends(get_current_admin)]):
    return admin
