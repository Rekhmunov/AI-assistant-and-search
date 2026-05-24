from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.schemas.admin import SettingsOut, SettingsUpdate
from app.services.admin_audit import log_admin_action
from app.services.app_settings import SETTING_KEYS, list_settings, set_setting

router = APIRouter(prefix="/settings", tags=["admin-settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("settings:read")),
):
    redis = await get_redis()
    data = await list_settings(db, redis)
    return SettingsOut(settings=data)


@router.patch("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("settings:write"))],
):
    redis = await get_redis()
    updated: dict[str, Any] = {}
    for key, value in body.settings.items():
        if key not in SETTING_KEYS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown setting: {key}")
        await set_setting(key, value, db, redis, admin.id)
        updated[key] = value

    await log_admin_action(
        db,
        admin=admin,
        action="settings.update",
        resource_type="settings",
        details=updated,
        ip_address=request.client.host if request.client else None,
    )
    data = await list_settings(db, redis)
    return SettingsOut(settings=data)
