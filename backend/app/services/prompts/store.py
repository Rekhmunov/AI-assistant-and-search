"""Чтение промптов из app_settings с fallback на defaults."""

from __future__ import annotations

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.app_settings import get_setting
from app.services.prompts.defaults import PROMPT_DEFAULTS


class PromptStore:
    def __init__(self, db: AsyncSession, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client

    async def get(self, prompt_id: str, *, default: str | None = None) -> str:
        fallback = default if default is not None else PROMPT_DEFAULTS.get(prompt_id, "")
        key = f"prompt_{prompt_id}"
        raw = await get_setting(key, self.db, self.redis)
        if isinstance(raw, str) and raw.strip():
            return raw
        return fallback
