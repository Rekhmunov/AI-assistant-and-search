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


def deepseek_key_suffix(settings: Settings | None = None) -> str | None:
    key = (settings or get_settings()).deepseek_api_key.strip()
    if len(key) < 8:
        return None
    return key[-4:]


def build_llm_runtime_status(
    active_provider: str,
    settings: Settings | None = None,
) -> dict:
    s = settings or get_settings()
    anthropic_loaded = s.anthropic_configured
    deepseek_loaded = s.deepseek_configured
    gigachat_loaded = s.gigachat_configured
    perplexity_loaded = s.perplexity_configured
    anthropic_mock = active_provider == "anthropic_claude" and not anthropic_loaded
    deepseek_mock = active_provider == "deepseek" and not deepseek_loaded
    gigachat_mock = active_provider == "gigachat" and not gigachat_loaded
    perplexity_mock = active_provider == "perplexity" and not perplexity_loaded
    hint: str | None = None
    if anthropic_mock:
        hint = (
            "В админке выбран Claude, но ANTHROPIC_API_KEY не виден backend-контейнеру. "
            "Проверьте /opt/aisearch/.env и выполните: "
            "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
        )
    elif deepseek_mock:
        hint = (
            "В админке выбран DeepSeek, но DEEPSEEK_API_KEY не виден backend-контейнеру. "
            "Проверьте /opt/aisearch/.env и выполните: "
            "docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker"
        )
    elif gigachat_mock:
        hint = (
            "В админке выбран GigaChat, но GIGACHAT_CREDENTIALS не виден backend-контейнеру. "
            "Проверьте /opt/aisearch/.env (scope GIGACHAT_API_PERS) и пересоздайте backend/worker."
        )
    elif perplexity_mock:
        hint = (
            "В админке выбран Perplexity, но PERPLEXITY_API_KEY не виден backend-контейнеру. "
            "Проверьте /opt/aisearch/.env и пересоздайте backend/worker."
        )
    elif active_provider == "yandex_gpt" and (anthropic_loaded or deepseek_loaded or gigachat_loaded or perplexity_loaded):
        hint = (
            "В .env есть ключ альтернативного LLM, но в БД активен Yandex GPT — "
            "смените LLM в админке и нажмите «Сохранить»."
        )
    return {
        "active_provider": active_provider,
        "anthropic_api_key_loaded": anthropic_loaded,
        "anthropic_key_suffix": anthropic_key_suffix(s),
        "anthropic_mock_active": anthropic_mock,
        "deepseek_api_key_loaded": deepseek_loaded,
        "deepseek_key_suffix": deepseek_key_suffix(s),
        "deepseek_mock_active": deepseek_mock,
        "gigachat_credentials_loaded": gigachat_loaded,
        "gigachat_mock_active": gigachat_mock,
        "perplexity_api_key_loaded": perplexity_loaded,
        "perplexity_mock_active": perplexity_mock,
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
    if status["deepseek_mock_active"]:
        logger.warning("LLM runtime: deepseek selected but DEEPSEEK_API_KEY missing — mock mode")
    if status["gigachat_mock_active"]:
        logger.warning("LLM runtime: gigachat selected but GIGACHAT_CREDENTIALS missing — mock mode")
    return status
