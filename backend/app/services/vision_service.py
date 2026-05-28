"""Vision: Claude или GigaChat по настройке админки."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.app_settings import get_setting
from app.services.attachment_bundle import VisionImage
from app.services.gigachat import GigaChatProvider
from app.services.prompts.defaults import DEFAULT_VISION_PROVIDER
from app.services.prompts.store import PromptStore
from app.services.providers.registry import VALID_VISION_IDS
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)

VISION_UNAVAILABLE_MSG = (
    "На данный момент обработка фотографий невозможна. "
    "Проверьте ключи vision-провайдера в .env на сервере или выберите другой провайдер в админке."
)


class VisionNotSupportedError(Exception):
    """Нет настроенного vision-провайдера."""


async def resolve_vision_provider_id(
    db: AsyncSession,
    redis_client: redis.Redis,
) -> str:
    raw = await get_setting("vision_provider", db, redis_client)
    pid = str(raw or DEFAULT_VISION_PROVIDER).strip()
    return pid if pid in VALID_VISION_IDS else DEFAULT_VISION_PROVIDER


def _create_vision_backend(
    provider_id: str,
    settings: Settings,
    prompt_store: PromptStore | None,
):
    if provider_id == "anthropic_claude":
        return AnthropicClaudeProvider(settings, prompt_store=prompt_store)
    if provider_id == "gigachat":
        return GigaChatProvider(settings, prompt_store=prompt_store)
    raise ValueError(f"Unknown vision provider: {provider_id}")


def _vision_configured(provider_id: str, settings: Settings) -> bool:
    if provider_id == "anthropic_claude":
        return settings.anthropic_configured
    if provider_id == "gigachat":
        return settings.gigachat_configured
    return False


async def summarize_vision_for_search(
    query: str,
    vision_images: list[VisionImage],
    history: list[tuple[str, str]],
    *,
    db: AsyncSession,
    redis_client: redis.Redis,
    prior_sources_block: str = "",
    settings: Settings | None = None,
    prompt_store: PromptStore | None = None,
) -> str:
    settings = settings or get_settings()
    provider_id = await resolve_vision_provider_id(db, redis_client)
    if not _vision_configured(provider_id, settings):
        raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG)
    backend = _create_vision_backend(provider_id, settings, prompt_store)
    if isinstance(backend, GigaChatProvider):
        return await backend.summarize_vision_for_search(
            query,
            vision_images,
            history,
            prior_sources_block=prior_sources_block,
        )
    if isinstance(backend, AnthropicClaudeProvider):
        parts: list[str] = []
        async for chunk in backend.stream_answer_vision(
            query,
            vision_images,
            history,
            model="lite",
            prior_sources_block=prior_sources_block,
        ):
            parts.append(chunk)
        return "".join(parts).strip()
    raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG)


async def stream_vision_answer(
    query: str,
    vision_images: list[VisionImage],
    history: list[tuple[str, str]],
    *,
    db: AsyncSession,
    redis_client: redis.Redis,
    model: str = "pro",
    prior_sources_block: str = "",
    settings: Settings | None = None,
    prompt_store: PromptStore | None = None,
) -> AsyncIterator[str]:
    settings = settings or get_settings()
    provider_id = await resolve_vision_provider_id(db, redis_client)
    if not _vision_configured(provider_id, settings):
        raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG)
    backend = _create_vision_backend(provider_id, settings, prompt_store)
    answer_model = "pro" if model == "pro" else "lite"
    try:
        if isinstance(backend, (AnthropicClaudeProvider, GigaChatProvider)):
            async for chunk in backend.stream_answer_vision(
                query,
                vision_images,
                history,
                model=answer_model,  # type: ignore[arg-type]
                prior_sources_block=prior_sources_block,
            ):
                yield chunk
            return
    except YandexServiceError:
        raise
    except Exception as e:
        logger.exception("Vision stream failed (%s)", provider_id)
        raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG) from e
    raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG)
