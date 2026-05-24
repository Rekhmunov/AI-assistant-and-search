from typing import Any

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.app_setting import AppSetting

SETTING_KEYS: dict[str, type] = {
    "free_searches_per_day": int,
    "pro_searches_per_day": int,
    "global_yandex_requests_per_day": int,
    "maintenance_mode": bool,
    "bot_welcome_text": str,
}

ENV_DEFAULTS: dict[str, str] = {
    "free_searches_per_day": "free_searches_per_day",
    "pro_searches_per_day": "pro_searches_per_day",
    "global_yandex_requests_per_day": "global_yandex_requests_per_day",
    "maintenance_mode": "false",
    "bot_welcome_text": "Привет! Нажмите кнопку ниже, чтобы открыть AI Search.",
}


def _redis_key(key: str) -> str:
    return f"setting:{key}"


def _parse_value(key: str, raw: str) -> Any:
    kind = SETTING_KEYS.get(key, str)
    if kind is bool:
        return raw.lower() in ("1", "true", "yes", "on")
    if kind is int:
        return int(raw)
    return raw


def _serialize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def default_for_key(key: str, settings: Settings | None = None) -> Any:
    settings = settings or get_settings()
    env_attr = ENV_DEFAULTS.get(key)
    if env_attr and hasattr(settings, env_attr):
        return getattr(settings, env_attr)
    if key == "maintenance_mode":
        return False
    if key == "bot_welcome_text":
        return ENV_DEFAULTS["bot_welcome_text"]
    return ""


async def sync_settings_cache(db: AsyncSession, redis_client: redis.Redis) -> None:
    result = await db.execute(select(AppSetting))
    rows = result.scalars().all()
    for row in rows:
        await redis_client.set(_redis_key(row.key), row.value)


async def get_setting(
    key: str,
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> Any:
    settings = settings or get_settings()
    cached = await redis_client.get(_redis_key(key))
    if cached is not None:
        return _parse_value(key, cached)

    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        await redis_client.set(_redis_key(key), row.value)
        return _parse_value(key, row.value)

    return default_for_key(key, settings)


async def set_setting(
    key: str,
    value: Any,
    db: AsyncSession,
    redis_client: redis.Redis,
    admin_id: Any,
) -> AppSetting:
    if key not in SETTING_KEYS:
        raise ValueError(f"Unknown setting: {key}")

    serialized = _serialize_value(value)
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = serialized
        row.updated_by_admin_id = admin_id
    else:
        row = AppSetting(key=key, value=serialized, updated_by_admin_id=admin_id)
        db.add(row)

    await db.flush()
    await redis_client.set(_redis_key(key), serialized)
    return row


async def list_settings(db: AsyncSession, redis_client: redis.Redis) -> dict[str, Any]:
    settings = get_settings()
    out: dict[str, Any] = {}
    for key in SETTING_KEYS:
        out[key] = await get_setting(key, db, redis_client, settings)
    out["yandex_configured"] = settings.yandex_configured
    out["environment"] = settings.environment
    return out
