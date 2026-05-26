from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.admin_user import AdminUser
from app.schemas.admin import SettingsBundleOut, SettingsUpdate
from app.services.admin_audit import log_admin_action
from app.services.app_settings import SETTING_KEYS, list_settings, list_settings_bundle, set_setting
from app.services.anthropic_probe import probe_anthropic
from app.services.deepseek_probe import probe_deepseek
from app.services.providers.registry import VALID_LLM_IDS, VALID_SEARCH_IDS

router = APIRouter(prefix="/settings", tags=["admin-settings"])


@router.get("", response_model=SettingsBundleOut)
async def get_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("settings:read")),
):
    redis = await get_redis()
    bundle = await list_settings_bundle(db, redis)
    return SettingsBundleOut(**bundle)


@router.patch("", response_model=SettingsBundleOut)
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
        if key == "llm_provider" and str(value) not in VALID_LLM_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown LLM provider")
        if key == "llm_provider" and str(value) == "anthropic_claude":
            if not get_settings().anthropic_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "ANTHROPIC_API_KEY не загружен в backend. "
                        "Добавьте ключ в /opt/aisearch/.env и выполните: "
                        "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
                    ),
                )
        if key == "llm_provider" and str(value) == "deepseek":
            if not get_settings().deepseek_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "DEEPSEEK_API_KEY не загружен в backend. "
                        "Добавьте ключ в /opt/aisearch/.env и выполните: "
                        "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
                    ),
                )
        if key == "search_provider" and str(value) not in VALID_SEARCH_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown search provider")
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
    bundle = await list_settings_bundle(db, redis)
    return SettingsBundleOut(**bundle)


@router.post("/probe-anthropic")
async def probe_anthropic_api(
    _admin=Depends(require_permission("settings:read")),
):
    """
    Тестовый запрос к Anthropic с ключом из .env контейнера.
    Должен появиться в Usage того ключа, чей суффикс в ответе.
    """
    return await probe_anthropic()


@router.post("/probe-deepseek")
async def probe_deepseek_api(
    _admin=Depends(require_permission("settings:read")),
):
    """Тестовый запрос к DeepSeek (lite + pro) с ключом из .env контейнера."""
    return await probe_deepseek()
