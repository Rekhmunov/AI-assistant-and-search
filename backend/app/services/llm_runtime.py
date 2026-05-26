"""Статус активного LLM и загрузки ключей из .env (для health и админки)."""

from __future__ import annotations

import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
logger = logging.getLogger(__name__)


def anthropic_key_suffix(settings: Settings | None = None) -> str | None:
    """Последние 4 символа ключа — чтобы сверить с console.anthropic.com (не секрет)."""
    key = (settings or get_settings()).anthropic_api_key.strip()
    if len(key) < 8:
        return None
    return key[-4:]


def build_llm_runtime_status(
    active_provider: str,
    settings: Settings | None = None,
) -> dict:
    s = settings or get_settings()
    loaded = s.anthropic_configured
    mock = active_provider == "anthropic_claude" and not loaded
    hint: str | None = None
    if mock:
        hint = (
            "В админке выбран Claude, но ANTHROPIC_API_KEY не виден backend-контейнеру. "
            "Проверьте /opt/aisearch/.env и выполните: "
            "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
        )
    elif active_provider == "yandex_gpt" and loaded:
        hint = "В .env есть Claude, но в БД активен Yandex GPT — смените LLM в админке и нажмите «Сохранить»."
    elif active_provider == "anthropic_claude" and loaded:
        hint = None
    return {
        "active_provider": active_provider,
        "anthropic_api_key_loaded": loaded,
        "anthropic_key_suffix": anthropic_key_suffix(s),
        "anthropic_mock_active": mock,
        "hint": hint,
    }


async def fetch_llm_runtime_status(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
) -> dict:
    from app.services.providers.factory import resolve_llm_provider_id

    active = await resolve_llm_provider_id(db, redis_client)
    status = build_llm_runtime_status(active, settings)
    if status["anthropic_mock_active"]:
        logger.warning("LLM runtime: anthropic_claude selected but ANTHROPIC_API_KEY missing — mock mode")
    return status
