"""Claude/DeepSeek с откатом на Yandex GPT или GigaChat при ошибке LLM API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Literal

from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.deepseek import DeepSeekProvider
from app.services.facts.models import FactPack
from app.services.llm_provider import SearchSource
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import YandexGPTProvider

logger = logging.getLogger(__name__)


async def _record_fallback_incident(primary_name: str, fallback_name: str, error: Exception) -> None:
    """Запускает запись инцидента в фоне — не блокирует fallback-ответ."""
    import asyncio as _asyncio
    _asyncio.create_task(_do_record_fallback(primary_name, fallback_name, error))


async def _do_record_fallback(primary_name: str, fallback_name: str, error: Exception) -> None:
    try:
        import redis.asyncio as aioredis
        from app.core.config import get_settings
        from app.services.service_incidents import record_service_incident
        settings = get_settings()
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await record_service_incident(
                redis_client,
                service="gpt",
                kind="fallback_activated",
                message=f"Переключение {primary_name} → {fallback_name}: {error!s:.300}",
            )
        finally:
            await redis_client.aclose()
    except Exception:
        logger.exception("_do_record_fallback failed")


class FreeLLMWithFallback:
    """
    Резервный провайдер для Lite-пользователей: DeepSeek ↔ GigaChat.
    Если выбран DeepSeek — при сбое переключается на GigaChat, и наоборот.
    При переключении записывает инцидент и отправляет email администратору.
    """

    def __init__(self, primary, fallback, primary_name: str, fallback_name: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self.prompts = getattr(primary, "prompts", None)
        self.prompt_namespace = getattr(primary, "prompt_namespace", "")
        self._last_label_provider = primary

    @property
    def label_provider(self):
        return self._last_label_provider

    async def get_prompt(self, suffix: str, default: str) -> str:
        return await self.primary.get_prompt(suffix, default)

    async def _on_fallback(self, error: YandexServiceError) -> None:
        logger.warning(
            "Free LLM %s failed, switching to %s: %s",
            self.primary_name, self.fallback_name, error,
        )
        self._last_label_provider = self.fallback
        await _record_fallback_incident(self.primary_name, self.fallback_name, error)

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        try:
            self._last_label_provider = self.primary
            return await self.primary.complete_text(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        except YandexServiceError as e:
            await self._on_fallback(e)
            return await self.fallback.complete_text(messages, model=model, max_tokens=max_tokens, temperature=temperature)

    async def _stream_with_fallback(self, cause: YandexServiceError, fallback_iter: AsyncIterator[str]) -> AsyncIterator[str]:
        await self._on_fallback(cause)
        async for chunk in fallback_iter:
            yield chunk

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
        intent_howto: bool = False,
        grounding_mode: str = "strict",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer(
                query, sources, history, model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify, strict_facts=strict_facts,
                fact_pack=fact_pack, intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            ):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer(
                query, sources, history, model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify, strict_facts=strict_facts,
                fact_pack=fact_pack, intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            )
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer_direct(query, history, model=model, prior_sources_block=prior_sources_block):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer_direct(query, history, model=model, prior_sources_block=prior_sources_block)
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        try:
            self._last_label_provider = self.primary
            return await self.primary.generate_follow_ups(query, answer)
        except YandexServiceError as e:
            logger.warning("Free LLM %s follow_ups failed, using %s: %s", self.primary_name, self.fallback_name, e)
            self._last_label_provider = self.fallback
            return await self.fallback.generate_follow_ups(query, answer)

    async def _build_messages_search(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_search(*args, **kwargs)

    async def _build_messages_direct(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_direct(*args, **kwargs)

AnswerModel = Literal["lite", "pro"]


class ClaudeWithYandexFallback:
    """Прокси: сначала Claude, при YandexServiceError — Yandex GPT (если настроен)."""

    prompt_namespace = "anthropic_claude"

    def __init__(
        self,
        primary: AnthropicClaudeProvider,
        fallback: YandexGPTProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.prompts = primary.prompts
        self._last_label_provider: AnthropicClaudeProvider | YandexGPTProvider = primary

    @property
    def label_provider(self) -> AnthropicClaudeProvider | YandexGPTProvider:
        return self._last_label_provider

    async def get_prompt(self, suffix: str, default: str) -> str:
        return await self.primary.get_prompt(suffix, default)

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        try:
            self._last_label_provider = self.primary
            return await self.primary.complete_text(
                messages, model=model, max_tokens=max_tokens, temperature=temperature
            )
        except YandexServiceError as e:
            return await self._fallback_complete(e, messages, model, max_tokens, temperature)

    async def _fallback_complete(
        self,
        cause: YandexServiceError,
        messages: list[dict],
        model: AnswerModel,
        max_tokens: int,
        temperature: float,
    ) -> str:
        if not self.fallback.settings.yandex_configured:
            raise cause
        logger.warning("Claude complete_text failed, using Yandex GPT: %s", cause)
        self._last_label_provider = self.fallback
        return await self.fallback.complete_text(
            messages, model=model, max_tokens=max_tokens, temperature=temperature
        )

    async def _stream_with_fallback(
        self,
        cause: YandexServiceError,
        fallback_iter: AsyncIterator[str],
    ) -> AsyncIterator[str]:
        if not self.fallback.settings.yandex_configured:
            raise cause
        logger.warning("Claude stream failed, using Yandex GPT: %s", cause)
        self._last_label_provider = self.fallback
        async for chunk in fallback_iter:
            yield chunk

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
        intent_howto: bool = False,
        grounding_mode: str = "strict",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer(
                query,
                sources,
                history,
                model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                fact_pack=fact_pack,
                intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            ):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer(
                query,
                sources,
                history,
                model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                fact_pack=fact_pack,
                intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            )
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer_direct(
                query, history, model=model, prior_sources_block=prior_sources_block
            ):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer_direct(
                query, history, model=model, prior_sources_block=prior_sources_block
            )
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        try:
            self._last_label_provider = self.primary
            return await self.primary.generate_follow_ups(query, answer)
        except YandexServiceError as e:
            if not self.fallback.settings.yandex_configured:
                raise
            logger.warning("Claude follow_ups failed, using Yandex GPT: %s", e)
            self._last_label_provider = self.fallback
            return await self.fallback.generate_follow_ups(query, answer)

    async def _build_messages_search(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_search(*args, **kwargs)

    async def _build_messages_direct(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_direct(*args, **kwargs)


class DeepSeekWithYandexFallback:
    """Прокси: сначала DeepSeek, при YandexServiceError — Yandex GPT (если настроен)."""

    prompt_namespace = "deepseek"

    def __init__(
        self,
        primary: DeepSeekProvider,
        fallback: YandexGPTProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.prompts = primary.prompts
        self._last_label_provider: DeepSeekProvider | YandexGPTProvider = primary

    @property
    def label_provider(self) -> DeepSeekProvider | YandexGPTProvider:
        return self._last_label_provider

    async def get_prompt(self, suffix: str, default: str) -> str:
        return await self.primary.get_prompt(suffix, default)

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        try:
            self._last_label_provider = self.primary
            return await self.primary.complete_text(
                messages, model=model, max_tokens=max_tokens, temperature=temperature
            )
        except YandexServiceError as e:
            return await self._fallback_complete(e, messages, model, max_tokens, temperature)

    async def _fallback_complete(
        self,
        cause: YandexServiceError,
        messages: list[dict],
        model: AnswerModel,
        max_tokens: int,
        temperature: float,
    ) -> str:
        if not self.fallback.settings.yandex_configured:
            raise cause
        logger.warning("DeepSeek complete_text failed, using Yandex GPT: %s", cause)
        self._last_label_provider = self.fallback
        return await self.fallback.complete_text(
            messages, model=model, max_tokens=max_tokens, temperature=temperature
        )

    async def _stream_with_fallback(
        self,
        cause: YandexServiceError,
        fallback_iter: AsyncIterator[str],
    ) -> AsyncIterator[str]:
        if not self.fallback.settings.yandex_configured:
            raise cause
        logger.warning("DeepSeek stream failed, using Yandex GPT: %s", cause)
        self._last_label_provider = self.fallback
        async for chunk in fallback_iter:
            yield chunk

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
        intent_howto: bool = False,
        grounding_mode: str = "strict",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer(
                query,
                sources,
                history,
                model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                fact_pack=fact_pack,
                intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            ):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer(
                query,
                sources,
                history,
                model=model,
                prior_sources_block=prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                fact_pack=fact_pack,
                intent_howto=intent_howto,
                grounding_mode=grounding_mode,
            )
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        try:
            self._last_label_provider = self.primary
            async for chunk in self.primary.stream_answer_direct(
                query, history, model=model, prior_sources_block=prior_sources_block
            ):
                yield chunk
        except YandexServiceError as e:
            fb = self.fallback.stream_answer_direct(
                query, history, model=model, prior_sources_block=prior_sources_block
            )
            async for chunk in self._stream_with_fallback(e, fb):
                yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        try:
            self._last_label_provider = self.primary
            return await self.primary.generate_follow_ups(query, answer)
        except YandexServiceError as e:
            if not self.fallback.settings.yandex_configured:
                raise
            logger.warning("DeepSeek follow_ups failed, using Yandex GPT: %s", e)
            self._last_label_provider = self.fallback
            return await self.fallback.generate_follow_ups(query, answer)

    async def _build_messages_search(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_search(*args, **kwargs)

    async def _build_messages_direct(self, *args, **kwargs) -> list[dict]:
        return await self.primary._build_messages_direct(*args, **kwargs)
