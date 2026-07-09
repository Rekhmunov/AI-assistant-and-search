"""Perplexity Sonar API — встроенный поиск + ответ (без Yandex Search)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_prompted import PromptedLLMMixin
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.perplexity_sources import map_perplexity_sources
from app.services.prompts.defaults import ANSWER_DIRECT, ANSWER_META, FOLLOW_UPS_SYSTEM
from app.services.prompts.store import PromptStore
from app.services.search_query import is_meta_assistant_query
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import (
    _query_has_document_block,
    _yield_text_paced,
)

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]

PERPLEXITY_PROVIDER_ID = "perplexity"

_SYSTEM_SEARCH = (
    "Ты — Glosix: умный ассистент с доступом к актуальному веб-поиску. "
    "Язык ответа: русский. Отвечай по сути, структурированно. "
    "Сохраняй ссылки на источники [1], [2] в тексте, если они есть в выдаче API."
)


@dataclass
class PerplexitySearchEvent:
    text: str | None = None
    sources: list[SearchSource] | None = None
    related_questions: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    model: str | None = None


def is_perplexity_provider(provider_id: str) -> bool:
    return provider_id == PERPLEXITY_PROVIDER_ID


def normalize_chat_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Perplexity: after optional system message(s), user/assistant must alternate."""
    normalized: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role not in ("system", "user", "assistant") or not content:
            continue
        if role == "system":
            normalized.append({"role": "system", "content": content})
            continue
        if normalized and normalized[-1]["role"] == role:
            merged = f"{normalized[-1]['content']}\n\n{content}"
            normalized[-1]["content"] = merged[:8000]
        else:
            normalized.append({"role": role, "content": content[:8000]})

    first_non_system = next(
        (i for i, msg in enumerate(normalized) if msg["role"] != "system"),
        len(normalized),
    )
    if first_non_system < len(normalized) and normalized[first_non_system]["role"] == "assistant":
        normalized.insert(first_non_system, {"role": "user", "content": "Продолжение диалога."})
    return normalized


class PerplexityProvider(PromptedLLMMixin, LLMProvider):
    prompt_namespace = "perplexity"

    def __init__(self, settings: Settings | None = None, *, prompt_store: PromptStore | None = None):
        self.settings = settings or get_settings()
        self.prompts = prompt_store
        self._last_related_questions: list[str] = []

    @property
    def configured(self) -> bool:
        return self.settings.perplexity_configured

    def _model_name(self, model: AnswerModel) -> str:
        if model == "pro":
            return self.settings.perplexity_model_pro  # sonar-pro для аналитических запросов
        return self.settings.perplexity_model_lite  # sonar для простых фактов и новостей

    def _chat_url(self) -> str:
        return f"{self.settings.perplexity_base_url.rstrip('/')}/v1/sonar"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.perplexity_api_key.strip()}",
            "Content-Type": "application/json",
        }

    def _http_client(self, *, timeout: float) -> httpx.AsyncClient:
        proxy = (self.settings.perplexity_http_proxy or "").strip() or None
        if proxy:
            return httpx.AsyncClient(timeout=timeout, proxy=proxy)
        return httpx.AsyncClient(timeout=timeout)

    def _history_messages(self, history: list[tuple[str, str]], *, max_turns: int = 6) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        for role, text in history[-max_turns * 2 :]:
            r = "assistant" if role == "assistant" else "user"
            t = (text or "").strip()
            if t:
                msgs.append({"role": r, "content": t[:4000]})
        return normalize_chat_messages(msgs)

    def _build_user_turn(
        self,
        query: str,
        *,
        prior_sources_block: str = "",
        max_chars: int = 6000,
    ) -> str:
        parts: list[str] = []
        extra = prior_sources_block.strip()
        if extra:
            parts.append(extra[:3000])
        parts.append((query or "").strip()[:4000])
        return "\n\n".join(p for p in parts if p)[:max_chars]

    def _parse_stream_event(self, event: dict) -> tuple[str | None, list[SearchSource] | None, list[str]]:
        text: str | None = None
        choices = event.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            # Используем только delta.content — не msg.content.
            # msg.content в streaming-чанках содержит весь накопленный текст,
            # что приводит к дублированию ответа.
            chunk = delta.get("content")
            if chunk:
                text = str(chunk)

        sources = map_perplexity_sources(
            search_results=event.get("search_results"),
            citations=event.get("citations"),
        )
        related = event.get("related_questions") or []
        rq = [str(x).strip() for x in related if str(x).strip()] if isinstance(related, list) else []
        return text, (sources or None), rq

    async def stream_search_answer(
        self,
        query: str,
        history: list[tuple[str, str]],
        *,
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[PerplexitySearchEvent]:
        """Sonar: поиск + ответ в одном вызове; источники из search_results/citations."""
        if not self.configured:
            mock_sources = [
                SearchSource(
                    index=1,
                    url="https://example.com",
                    title="Mock Perplexity",
                    snippet="Задайте PERPLEXITY_API_KEY",
                    domain="example.com",
                )
            ]
            yield PerplexitySearchEvent(sources=mock_sources)
            async for part in _yield_text_paced("Ответ в режиме mock (PERPLEXITY_API_KEY не задан). [1]"):
                yield PerplexitySearchEvent(text=part)
            return

        model_id = self._model_name(model)
        messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_SEARCH}]
        messages.extend(self._history_messages(history))
        messages.append(
            {
                "role": "user",
                "content": self._build_user_turn(query, prior_sources_block=prior_sources_block),
            }
        )
        messages = normalize_chat_messages(messages)

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            # stream_mode: "full" removed — it is non-standard and caused Perplexity to
            # send the FULL accumulated text in every delta.content chunk instead of
            # incremental deltas, breaking the _accumulated dedup logic.
            "return_related_questions": self.settings.perplexity_return_related_questions,
            "language_preference": "ru",
            "max_tokens": 2800,
            "temperature": 0.2,
            # Pro запросы читают больше источников (high), lite — быстрее (low)
            "search_context_size": "high" if model == "pro" else "low",
        }
        recency = (self.settings.perplexity_search_recency_filter or "").strip()
        if recency:
            payload["search_recency_filter"] = recency

        last_sources: list[SearchSource] | None = None
        last_related: list[str] = []
        last_usage: dict[str, Any] | None = None
        sources_sent = False

        try:
            async with self._http_client(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    self._chat_url(),
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise YandexServiceError(
                            "perplexity",
                            f"Perplexity недоступен (HTTP {response.status_code}): {body}",
                            response.status_code,
                        )
                    _search_emitted = ""  # total text we have yielded so far
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if event.get("usage"):
                            last_usage = event.get("usage")
                        if event.get("model"):
                            model_id = str(event["model"])

                        text, sources, related = self._parse_stream_event(event)
                        if sources:
                            last_sources = sources
                        if related:
                            last_related = related

                        if sources and not sources_sent:
                            sources_sent = True
                            yield PerplexitySearchEvent(sources=sources, model=model_id)

                        if text:
                            if text == _search_emitted:
                                # Exact duplicate of full text (final chunk repeat) — skip
                                continue
                            # Detect "full-text" chunk: text starts with what we already emitted
                            # and is longer → only yield the NEW suffix
                            if _search_emitted and text.startswith(_search_emitted):
                                new_part = text[len(_search_emitted):]
                                if new_part:
                                    _search_emitted = text
                                    yield PerplexitySearchEvent(text=new_part, model=model_id)
                            else:
                                # Normal incremental delta
                                _search_emitted += text
                                yield PerplexitySearchEvent(text=text, model=model_id)

        except httpx.HTTPError as e:
            logger.exception("Perplexity stream failed")
            raise YandexServiceError("perplexity", "Perplexity недоступен (сеть)") from e

        self._last_related_questions = last_related[:3]
        if last_sources and not sources_sent:
            yield PerplexitySearchEvent(sources=last_sources, model=model_id)
        if last_related or last_usage:
            yield PerplexitySearchEvent(
                related_questions=last_related,
                usage=last_usage,
                model=model_id,
            )

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        async for event in self.stream_search_answer(
            query,
            history,
            model=model,
            prior_sources_block=prior_sources_block,
        ):
            if event.text:
                yield event.text

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Ответ по контексту (mock Perplexity)."):
                yield part
            return

        if _query_has_document_block(query):
            system = await self.get_prompt("answer_document", ANSWER_DIRECT)
        elif is_meta_assistant_query(query):
            system = await self.get_prompt("answer_meta", ANSWER_META)
        else:
            system = await self.get_prompt("answer_direct", ANSWER_DIRECT)

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        messages.extend(self._history_messages(history))
        messages.append(
            {
                "role": "user",
                "content": self._build_user_turn(query, prior_sources_block=prior_sources_block),
            }
        )
        messages = normalize_chat_messages(messages)

        payload = {
            "model": self._model_name(model),
            "messages": messages,
            "stream": True,
            "disable_search": True,
            "max_tokens": 2000,
            "temperature": 0.35,
        }

        try:
            async with self._http_client(timeout=90.0) as client:
                async with client.stream(
                    "POST",
                    self._chat_url(),
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:400]
                        raise YandexServiceError(
                            "perplexity",
                            f"Perplexity direct HTTP {response.status_code}: {body}",
                            response.status_code,
                        )
                    _emitted = ""
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        text, _, _ = self._parse_stream_event(event)
                        if text:
                            if text == _emitted:
                                # Exact duplicate of full text — skip
                                continue
                            if _emitted and text.startswith(_emitted):
                                # Full-text chunk: only yield the new suffix
                                new_part = text[len(_emitted):]
                                if new_part:
                                    _emitted = text
                                    yield new_part
                            else:
                                # Normal incremental delta
                                _emitted += text
                                yield text
        except httpx.HTTPError as e:
            raise YandexServiceError("perplexity", "Perplexity недоступен (сеть)") from e

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        if self._last_related_questions:
            return self._last_related_questions[:3]

        from app.services.yandex_gpt import _default_follow_up_suggestions

        if not self.configured:
            return _default_follow_up_suggestions(query)

        system = await self.get_prompt("follow_ups_system", FOLLOW_UPS_SYSTEM)
        payload = {
            "model": self._model_name("lite"),
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Вопрос: {query[:500]}\n\nОтвет:\n{answer[:2000]}",
                },
            ],
            "disable_search": True,
            "max_tokens": 200,
            "temperature": 0.4,
        }
        try:
            async with self._http_client(timeout=45.0) as client:
                resp = await client.post(self._chat_url(), headers=self._headers(), json=payload)
                resp.raise_for_status()
                data = resp.json()
                text, _, _ = self._parse_stream_event(data)
                if not text:
                    return _default_follow_up_suggestions(query)
                lines = [ln.strip(" •-\t") for ln in text.splitlines() if ln.strip()]
                return [ln for ln in lines if len(ln) > 3][:3] or _default_follow_up_suggestions(query)
        except Exception:
            logger.exception("Perplexity follow-ups failed")
            return _default_follow_up_suggestions(query)
