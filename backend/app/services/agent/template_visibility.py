"""Управление видимостью шаблонов агентов."""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.templates import TEMPLATE_TITLES
from app.services.app_settings import get_setting, set_setting

logger = logging.getLogger(__name__)

SETTING_KEY = "agent_template_visibility"

# Все доступные шаблоны
ALL_TEMPLATES = list(TEMPLATE_TITLES.keys())


def _default_visibility() -> dict:
    return {tid: {"mode": "all", "user_ids": []} for tid in ALL_TEMPLATES}


async def get_template_visibility(
    db: AsyncSession, redis_client: redis.Redis
) -> dict[str, dict]:
    """
    Возвращает словарь видимости по шаблонам.
    Формат: {template_id: {"mode": "all"|"users", "user_ids": [int, ...]}}
    """
    raw = await get_setting(SETTING_KEY, db, redis_client)
    if not raw:
        return _default_visibility()
    try:
        data = json.loads(str(raw))
        if not isinstance(data, dict):
            return _default_visibility()
    except (json.JSONDecodeError, TypeError):
        return _default_visibility()

    result = _default_visibility()
    for tid, cfg in data.items():
        if tid in ALL_TEMPLATES and isinstance(cfg, dict):
            mode = str(cfg.get("mode") or "all")
            if mode not in ("all", "users"):
                mode = "all"
            # Поддерживаем как UUID-строки (новый формат), так и int (legacy)
            user_ids = [str(x) for x in (cfg.get("user_ids") or []) if x]
            result[tid] = {"mode": mode, "user_ids": user_ids}
    return result


async def set_template_visibility(
    db: AsyncSession,
    redis_client: redis.Redis,
    template_id: str,
    mode: str,
    user_ids: list[str],
    admin_id,
) -> dict[str, dict]:
    """Обновляет настройки видимости одного шаблона."""
    if template_id not in ALL_TEMPLATES:
        raise ValueError(f"Unknown template: {template_id}")
    if mode not in ("all", "users"):
        raise ValueError("mode must be 'all' or 'users'")

    current = await get_template_visibility(db, redis_client)
    current[template_id] = {"mode": mode, "user_ids": user_ids}

    await set_setting(SETTING_KEY, json.dumps(current), db, redis_client, admin_id)
    return current


def is_template_visible_for_user(
    visibility: dict[str, dict], template_id: str, user_id
) -> bool:
    """Проверяет, виден ли шаблон конкретному пользователю (user_id — UUID или str)."""
    cfg = visibility.get(template_id, {"mode": "all", "user_ids": []})
    if cfg.get("mode") == "all":
        return True
    return str(user_id) in [str(uid) for uid in (cfg.get("user_ids") or [])]
