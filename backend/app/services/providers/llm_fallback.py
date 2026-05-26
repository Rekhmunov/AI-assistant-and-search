"""Claude с откатом на Yandex GPT, если Anthropic вернул 403/сеть."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Literal

from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.facts.models import FactPack
from app.services.llm_provider import SearchSource
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import YandexGPTProvider

logger = logging.getLogger(__name__)

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
