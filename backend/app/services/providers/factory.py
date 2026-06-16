"""Runtime-выбор LLM/search провайдеров по plan пользователя и настройкам админки."""

from __future__ import annotations

from typing import Union

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.user import Plan, User
from app.services.app_settings import get_setting
from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.deepseek import DeepSeekProvider
from app.services.gigachat import GigaChatProvider
from app.services.perplexity import PerplexityProvider
from app.services.prompts.defaults import DEFAULT_FREE_LLM_PROVIDER, DEFAULT_LLM_PROVIDER, DEFAULT_SEARCH_PROVIDER
from app.services.prompts.store import PromptStore
from app.services.providers.llm_fallback import ClaudeWithYandexFallback, DeepSeekWithYandexFallback, FreeLLMWithFallback
from app.services.providers.registry import VALID_FREE_LLM_IDS, VALID_LLM_IDS, VALID_SEARCH_IDS
from app.services.yandex_gpt import YandexGPTProvider
from app.services.yandex_search import YandexSearchService

ChatLLM = Union[
    YandexGPTProvider,
    AnthropicClaudeProvider,
    DeepSeekProvider,
    GigaChatProvider,
    PerplexityProvider,
    ClaudeWithYandexFallback,
    DeepSeekWithYandexFallback,
    FreeLLMWithFallback,
]


async def resolve_llm_provider_id(db: AsyncSession, redis_client: redis.Redis) -> str:
    raw = await get_setting("llm_provider", db, redis_client)
    pid = str(raw or DEFAULT_LLM_PROVIDER).strip()
    return pid if pid in VALID_LLM_IDS else DEFAULT_LLM_PROVIDER


async def resolve_free_llm_provider_id(db: AsyncSession, redis_client: redis.Redis) -> str:
    raw = await get_setting("free_llm_provider", db, redis_client)
    pid = str(raw or DEFAULT_FREE_LLM_PROVIDER).strip()
    return pid if pid in VALID_FREE_LLM_IDS else DEFAULT_FREE_LLM_PROVIDER


async def resolve_llm_provider_id_for_user(
    db: AsyncSession,
    redis_client: redis.Redis,
    user: User | None,
) -> str:
    if user is not None and user.plan == Plan.PRO:
        return await resolve_llm_provider_id(db, redis_client)
    return await resolve_free_llm_provider_id(db, redis_client)


async def resolve_search_provider_id(db: AsyncSession, redis_client: redis.Redis) -> str:
    raw = await get_setting("search_provider", db, redis_client)
    pid = str(raw or DEFAULT_SEARCH_PROVIDER).strip()
    return pid if pid in VALID_SEARCH_IDS else DEFAULT_SEARCH_PROVIDER


def create_llm_provider(
    provider_id: str,
    settings: Settings | None,
    prompt_store: PromptStore,
) -> ChatLLM:
    settings = settings or get_settings()
    if provider_id == "yandex_gpt":
        return YandexGPTProvider(settings, prompt_store=prompt_store)
    if provider_id == "anthropic_claude":
        return AnthropicClaudeProvider(settings, prompt_store=prompt_store)
    if provider_id == "deepseek":
        return DeepSeekProvider(settings, prompt_store=prompt_store)
    if provider_id == "gigachat":
        return GigaChatProvider(settings, prompt_store=prompt_store)
    if provider_id == "perplexity":
        return PerplexityProvider(settings, prompt_store=prompt_store)
    raise ValueError(f"Unknown LLM provider: {provider_id}")


def create_search_provider(provider_id: str, settings: Settings | None) -> YandexSearchService:
    settings = settings or get_settings()
    if provider_id == "yandex_search":
        return YandexSearchService(settings)
    if provider_id == "claude_search":
        # Claude Search не использует Yandex; возвращаем заглушку,
        # которая никогда не вызывается когда _is_claude_search=True
        return YandexSearchService(settings)
    raise ValueError(f"Unknown search provider: {provider_id}")


def llm_model_label(llm: ChatLLM, answer_model: str) -> str:
    target = getattr(llm, "label_provider", llm)
    if isinstance(target, (AnthropicClaudeProvider, DeepSeekProvider, GigaChatProvider, PerplexityProvider)):
        return target._model_name(answer_model)  # type: ignore[arg-type]
    return target._model_uri(answer_model)  # type: ignore[arg-type]


def _wrap_llm_fallback(llm_id: str, llm: ChatLLM, settings: Settings, prompt_store: PromptStore) -> ChatLLM:
    import logging

    log = logging.getLogger(__name__)
    if llm_id == "anthropic_claude" and settings.yandex_configured:
        yandex_llm = YandexGPTProvider(settings, prompt_store=prompt_store)
        return ClaudeWithYandexFallback(llm, yandex_llm)  # type: ignore[assignment]
    if llm_id == "anthropic_claude" and not settings.anthropic_configured:
        log.warning(
            "llm_provider=anthropic_claude but ANTHROPIC_API_KEY missing — answers use mock, no API calls"
        )
    elif llm_id == "deepseek":
        # Lite: DeepSeek выбран основным → GigaChat резервный (если настроен)
        if settings.gigachat_configured:
            fallback_llm = GigaChatProvider(settings, prompt_store=prompt_store)
            return FreeLLMWithFallback(llm, fallback_llm, "DeepSeek", "GigaChat")  # type: ignore[return-value]
        elif settings.yandex_configured:
            yandex_llm = YandexGPTProvider(settings, prompt_store=prompt_store)
            return DeepSeekWithYandexFallback(llm, yandex_llm)  # type: ignore[assignment]
        elif not settings.deepseek_configured:
            log.warning("llm_provider=deepseek but DEEPSEEK_API_KEY missing — answers use mock, no API calls")
    elif llm_id == "gigachat":
        # Lite: GigaChat выбран основным → DeepSeek резервный (если настроен)
        if settings.deepseek_configured:
            fallback_llm = DeepSeekProvider(settings, prompt_store=prompt_store)
            return FreeLLMWithFallback(llm, fallback_llm, "GigaChat", "DeepSeek")  # type: ignore[return-value]
        if not settings.gigachat_configured:
            log.warning("llm_provider=gigachat but GIGACHAT_CREDENTIALS missing — answers use mock")
    elif llm_id == "perplexity" and not settings.perplexity_configured:
        log.warning(
            "llm_provider=perplexity but PERPLEXITY_API_KEY missing — answers use mock"
        )
    return llm


async def resolve_runtime_providers(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings | None = None,
    user: User | None = None,
) -> tuple[ChatLLM, YandexSearchService, PromptStore, str, str]:
    settings = settings or get_settings()
    prompt_store = PromptStore(db, redis_client)
    llm_id = await resolve_llm_provider_id_for_user(db, redis_client, user)
    search_id = await resolve_search_provider_id(db, redis_client)
    llm = create_llm_provider(llm_id, settings, prompt_store)
    llm = _wrap_llm_fallback(llm_id, llm, settings, prompt_store)
    search = create_search_provider(search_id, settings)
    return llm, search, prompt_store, llm_id, search_id
