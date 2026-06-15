"""Vision: Alice VLM, GigaChat или Claude с fallback-цепочкой."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.services.alice_vlm import AliceVLMProvider
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

# Приоритет Vision: Claude → GigaChat (Alice VLM как последний резерв).
# Выбранный в админке провайдер ставится первым, остальные — в этом порядке.
VISION_FALLBACK_ORDER: tuple[str, ...] = ("anthropic_claude", "gigachat", "alice_vlm")

_VISION_REFUSAL_RE = re.compile(
    r"(не\s+могу\s+(помочь|обработать|анализировать|рассмотреть|просмотреть)"
    r"|отказываюсь"
    r"|i\s+can(?:not|'t)\s+(help|assist|process|analyze))",
    re.IGNORECASE,
)


class VisionNotSupportedError(Exception):
    """Нет настроенного vision-провайдера."""


_PROVIDER_LABELS = {
    "anthropic_claude": "Claude",
    "gigachat": "GigaChat",
    "alice_vlm": "Alice VLM",
}


async def _record_vision_fallback(
    primary: str,
    fallback: str,
    error: Exception,
    redis_client,
) -> None:
    """Записывает инцидент переключения Vision-провайдера и отправляет email."""
    try:
        from app.services.service_incidents import record_service_incident
        primary_label = _PROVIDER_LABELS.get(primary, primary)
        fallback_label = _PROVIDER_LABELS.get(fallback, fallback)
        await record_service_incident(
            redis_client,
            service="vision",
            kind="fallback_activated",
            message=f"Vision: {primary_label} → {fallback_label}: {error!s:.300}",
        )
    except Exception:
        logger.exception("_record_vision_fallback failed")


class VisionProviderRefusedError(YandexServiceError):
    """Модель отказала или вернула пустой/бесполезный ответ — пробуем следующий провайдер."""


async def resolve_vision_provider_id(
    db: AsyncSession,
    redis_client: redis.Redis,
) -> str:
    raw = await get_setting("vision_provider", db, redis_client)
    pid = str(raw or DEFAULT_VISION_PROVIDER).strip()
    return pid if pid in VALID_VISION_IDS else DEFAULT_VISION_PROVIDER


def build_vision_fallback_chain(primary: str) -> tuple[str, ...]:
    pid = primary if primary in VALID_VISION_IDS else DEFAULT_VISION_PROVIDER
    tail = [p for p in VISION_FALLBACK_ORDER if p != pid]
    return (pid, *tail)


def _create_vision_backend(
    provider_id: str,
    settings: Settings,
    prompt_store: PromptStore | None,
):
    if provider_id == "alice_vlm":
        return AliceVLMProvider(settings, prompt_store=prompt_store)
    if provider_id == "anthropic_claude":
        return AnthropicClaudeProvider(settings, prompt_store=prompt_store)
    if provider_id == "gigachat":
        return GigaChatProvider(settings, prompt_store=prompt_store)
    raise ValueError(f"Unknown vision provider: {provider_id}")


def _vision_configured(provider_id: str, settings: Settings) -> bool:
    if provider_id == "alice_vlm":
        return settings.yandex_configured
    if provider_id == "anthropic_claude":
        return settings.anthropic_configured
    if provider_id == "gigachat":
        return settings.gigachat_configured
    return False


def _looks_like_refusal(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 500:
        return False
    return bool(_VISION_REFUSAL_RE.search(stripped))


def _check_vision_text(text: str, provider_id: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise VisionProviderRefusedError("gpt", f"{provider_id}: пустой ответ vision")
    if _looks_like_refusal(cleaned):
        raise VisionProviderRefusedError("gpt", f"{provider_id}: отказ модели vision")
    return cleaned


async def _summarize_with_provider(
    provider_id: str,
    query: str,
    vision_images: list[VisionImage],
    history: list[tuple[str, str]],
    *,
    settings: Settings,
    prompt_store: PromptStore | None,
    prior_sources_block: str,
) -> str:
    backend = _create_vision_backend(provider_id, settings, prompt_store)
    if isinstance(backend, GigaChatProvider):
        text = await backend.summarize_vision_for_search(
            query,
            vision_images,
            history,
            prior_sources_block=prior_sources_block,
        )
        return _check_vision_text(text, provider_id)
    if isinstance(backend, AliceVLMProvider):
        text = await backend.summarize_vision_for_search(
            query,
            vision_images,
            history,
            prior_sources_block=prior_sources_block,
        )
        return _check_vision_text(text, provider_id)
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
        return _check_vision_text("".join(parts), provider_id)
    raise VisionProviderRefusedError("gpt", f"{provider_id}: не поддерживается")


async def _stream_with_provider(
    provider_id: str,
    query: str,
    vision_images: list[VisionImage],
    history: list[tuple[str, str]],
    *,
    settings: Settings,
    prompt_store: PromptStore | None,
    model: str,
    prior_sources_block: str,
) -> AsyncIterator[str]:
    backend = _create_vision_backend(provider_id, settings, prompt_store)
    answer_model = "pro" if model == "pro" else "lite"
    if not isinstance(backend, (AliceVLMProvider, AnthropicClaudeProvider, GigaChatProvider)):
        raise VisionProviderRefusedError("gpt", f"{provider_id}: не поддерживается")

    parts: list[str] = []
    async for chunk in backend.stream_answer_vision(
        query,
        vision_images,
        history,
        model=answer_model,  # type: ignore[arg-type]
        prior_sources_block=prior_sources_block,
    ):
        parts.append(chunk)
        yield chunk

    try:
        _check_vision_text("".join(parts), provider_id)
    except VisionProviderRefusedError:
        if not parts:
            raise
        logger.warning(
            "Vision post-check refusal (%s), but response already streamed to client",
            provider_id,
        )


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
    primary = await resolve_vision_provider_id(db, redis_client)
    chain = build_vision_fallback_chain(primary)
    last_error: Exception | None = None

    succeeded_provider: str | None = None
    for provider_id in chain:
        if not _vision_configured(provider_id, settings):
            continue
        try:
            result = await _summarize_with_provider(
                provider_id,
                query,
                vision_images,
                history,
                settings=settings,
                prompt_store=prompt_store,
                prior_sources_block=prior_sources_block,
            )
            logger.info("Vision summary succeeded provider=%s", provider_id)
            succeeded_provider = provider_id
            if last_error is not None and provider_id != chain[0]:
                # Переключились на резервный — записываем инцидент
                await _record_vision_fallback(chain[0], provider_id, last_error, redis_client)
            return result
        except (YandexServiceError, VisionProviderRefusedError) as e:
            logger.warning("Vision summary failed (%s), trying next provider: %s", provider_id, e)
            last_error = e
        except Exception as e:
            logger.exception("Vision summary unexpected error (%s)", provider_id)
            last_error = e

    if last_error:
        raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG) from last_error
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
    primary = await resolve_vision_provider_id(db, redis_client)
    chain = build_vision_fallback_chain(primary)
    last_error: Exception | None = None

    for provider_id in chain:
        if not _vision_configured(provider_id, settings):
            continue
        try:
            async for chunk in _stream_with_provider(
                provider_id,
                query,
                vision_images,
                history,
                settings=settings,
                prompt_store=prompt_store,
                model=model,
                prior_sources_block=prior_sources_block,
            ):
                yield chunk
            logger.info("Vision stream succeeded provider=%s", provider_id)
            if last_error is not None and provider_id != chain[0]:
                await _record_vision_fallback(chain[0], provider_id, last_error, redis_client)
            return
        except (YandexServiceError, VisionProviderRefusedError) as e:
            logger.warning("Vision stream failed (%s), trying next provider: %s", provider_id, e)
            last_error = e
        except Exception as e:
            logger.exception("Vision stream unexpected error (%s)", provider_id)
            last_error = e

    if last_error:
        raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG) from last_error
    raise VisionNotSupportedError(VISION_UNAVAILABLE_MSG)
