import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.core import config as app_config
from app.models.admin_user import AdminUser
from app.schemas.admin import SettingsBundleOut, SettingsUpdate
from app.services.admin_audit import log_admin_action
from app.services.app_settings import SETTING_KEYS, list_settings, list_settings_bundle, set_setting
from app.services.anthropic_probe import probe_anthropic
from app.services.deepseek_probe import probe_deepseek
from app.services.gigachat_probe import probe_gigachat
from app.services.perplexity_probe import probe_perplexity
from app.services.providers.registry import (
    VALID_AGENT_LLM_IDS,
    VALID_FREE_LLM_IDS,
    VALID_IMAGE_GEN_IDS,
    VALID_LLM_IDS,
    VALID_SEARCH_IDS,
    VALID_VISION_IDS,
)

router = APIRouter(prefix="/settings", tags=["admin-settings"])


def _audit_settings_details(updated: dict[str, Any]) -> dict[str, Any]:
    """Не пишем полные промпты в audit (огромный JSON → риск 500 на commit)."""
    out: dict[str, Any] = {}
    for key, value in updated.items():
        if key.startswith("prompt_"):
            out[key] = {"chars": len(str(value))}
        else:
            out[key] = value
    return out


@router.get("", response_model=SettingsBundleOut)
async def read_settings_bundle(
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
    env = app_config.get_settings()
    updated: dict[str, Any] = {}
    for key, value in body.settings.items():
        if key not in SETTING_KEYS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неизвестный параметр настроек: {key}")
        if key == "llm_provider" and str(value) not in VALID_LLM_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный LLM-провайдер")
        if key == "free_llm_provider" and str(value) not in VALID_FREE_LLM_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер Free-плана")
        if key == "free_llm_provider" and str(value) == "deepseek":
            if not env.deepseek_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DEEPSEEK_API_KEY не загружен — Free-провайдер DeepSeek недоступен.",
                )
        if key == "free_llm_provider" and str(value) == "gigachat":
            if not env.gigachat_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GIGACHAT_CREDENTIALS не загружен — Free-провайдер GigaChat недоступен.",
                )
        if key == "llm_provider" and str(value) == "anthropic_claude":
            if not env.anthropic_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "ANTHROPIC_API_KEY не загружен в backend. "
                        "Добавьте ключ в /opt/aisearch/.env и выполните: "
                        "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
                    ),
                )
        if key == "llm_provider" and str(value) == "deepseek":
            if not env.deepseek_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "DEEPSEEK_API_KEY не загружен в backend. "
                        "Добавьте ключ в /opt/aisearch/.env и выполните: "
                        "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
                    ),
                )
        if key == "agent_llm_provider" and str(value) not in VALID_AGENT_LLM_IDS and str(value) != "":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный LLM-провайдер для агентов")
        if key == "agent_llm_provider" and str(value) == "anthropic_claude":
            if not env.anthropic_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ANTHROPIC_API_KEY не загружен — Claude для агентов недоступен.",
                )
        if key == "agent_llm_provider" and str(value) == "deepseek":
            if not env.deepseek_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DEEPSEEK_API_KEY не загружен — DeepSeek для агентов недоступен.",
                )
        if key == "agent_llm_provider" and str(value) == "gigachat":
            if not env.gigachat_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GIGACHAT_CREDENTIALS не загружен — GigaChat для агентов недоступен.",
                )
        if key == "search_provider" and str(value) not in VALID_SEARCH_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер поиска")
        if key == "vision_provider" and str(value) not in VALID_VISION_IDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер vision")
        if key == "vision_provider" and str(value) == "anthropic_claude":
            if not env.anthropic_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "ANTHROPIC_API_KEY не загружен в backend — vision через Claude недоступен."
                    ),
                )
        if key == "vision_provider" and str(value) == "alice_vlm":
            if not env.yandex_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "YANDEX_FOLDER_ID / YANDEX_API_KEY не загружены в backend — "
                        "vision через Alice AI VLM недоступен."
                    ),
                )
        if key == "vision_provider" and str(value) == "gigachat":
            if not env.gigachat_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "GIGACHAT_CREDENTIALS не загружен в backend — vision через GigaChat недоступен."
                    ),
                )
        if key == "image_gen_provider" and str(value) not in VALID_IMAGE_GEN_IDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неизвестный провайдер генерации изображений",
            )
        if key == "image_gen_provider" and str(value) == "gigachat":
            if not env.gigachat_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GIGACHAT_CREDENTIALS не загружен — генерация изображений недоступна.",
                )
        if key == "max_upload_mb_free":
            try:
                v = int(value)
                if v < 1 or v > 100:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Лимит загрузки Free: от 1 до 100 МБ")
        if key == "max_upload_mb_pro":
            try:
                v = int(value)
                if v < 1 or v > 500:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Лимит загрузки Pro: от 1 до 500 МБ")
        if key == "max_zip_mb_free":
            try:
                v = int(value)
                if v < 1 or v > 500:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Лимит ZIP Free: от 1 до 500 МБ")
        if key == "max_zip_mb_pro":
            try:
                v = int(value)
                if v < 1 or v > 2000:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Лимит ZIP Pro: от 1 до 2000 МБ")
        if key == "yandex_metrica_counter_id":
            val = str(value).strip()
            if val and not val.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ID счётчика Яндекс.Метрики должен содержать только цифры",
                )
        if key == "yandex_webmaster_verification":
            val = str(value).strip().lower()
            if val and not re.fullmatch(r"[a-f0-9]+", val):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Код верификации Вебмастера: только латинские буквы a–f и цифры",
                )
        if key == "pro_price_rub":
            try:
                price = int(value)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Цена Pro должна быть целым числом рублей",
                ) from None
            if price < 1 or price > 1_000_000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Цена Pro должна быть от 1 до 1 000 000 ₽",
                )
        if key == "llm_provider" and str(value) == "gigachat":
            if not env.gigachat_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "GIGACHAT_CREDENTIALS не загружен в backend. "
                        "Добавьте ключ в /opt/aisearch/.env и пересоздайте backend/worker."
                    ),
                )
        if key == "llm_provider" and str(value) == "perplexity":
            if not env.perplexity_configured:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "PERPLEXITY_API_KEY не загружен в backend. "
                        "Проверьте строку PERPLEXITY_API_KEY=pplx-... в /opt/aisearch/.env "
                        "(без пробелов вокруг =), затем: "
                        "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker. "
                        "Диагностика: curl -s https://api.glosix.ru/health | jq .perplexity_configured"
                    ),
                )
        await set_setting(key, value, db, redis, admin.id)
        updated[key] = value

    await log_admin_action(
        db,
        admin=admin,
        action="settings.update",
        resource_type="settings",
        details=_audit_settings_details(updated),
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


@router.post("/probe-gigachat")
async def probe_gigachat_api(
    _admin=Depends(require_permission("settings:read")),
):
    """Тестовый запрос к GigaChat (OAuth, lite + pro) с credentials из .env."""
    return await probe_gigachat()


@router.post("/probe-perplexity")
async def probe_perplexity_api(
    _admin=Depends(require_permission("settings:read")),
):
    """Тестовый запрос к Perplexity Sonar (disable_search) с ключом из .env."""
    return await probe_perplexity()
