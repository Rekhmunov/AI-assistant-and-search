"""Claude (Anthropic API) — тот же пайплайн Glosix, другой LLM."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.answer_guard import answer_addon_for_slots, strict_answer_addon
from app.services.facts.format import format_fact_pack_for_prompt
from app.services.facts.models import FactPack
from app.services.facts.slots import uses_synthesis_grounding
from app.services.llm_prompted import PromptedLLMMixin
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.prompts.defaults import (
    ANSWER_DIRECT,
    ANSWER_DOCUMENT,
    ANSWER_META,
    ANSWER_SEARCH,
    FOLLOW_UPS_SYSTEM,
)
from app.services.prompts.store import PromptStore
from app.services.search_query import is_meta_assistant_query
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import (
    _format_history,
    _format_sources,
    _query_has_document_block,
    _yield_text_paced,
)

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def _anthropic_http_error_message(response: httpx.Response, *, model: str) -> str:
    """Текст для UI: 403 чаще всего = нет доступа к модели в консоли Anthropic."""
    detail = ""
    try:
        data = response.json()
        err = data.get("error")
        if isinstance(err, dict):
            detail = str(err.get("message") or "").strip()
        elif err:
            detail = str(err).strip()
    except Exception:
        detail = (response.text or "").strip()[:240]

    base = f"Claude недоступен (HTTP {response.status_code})"
    if model:
        base += f", модель {model}"
    if detail:
        base += f": {detail}"
    if response.status_code == 403:
        base += (
            ". Частые причины: (1) Model access в console.anthropic.com для workspace ключа; "
            "(2) запрос с IP VPS/датацентра — Anthropic блокирует регион/хостинг "
            "(проверьте curl с сервера; решение: ANTHROPIC_HTTP_PROXY в .env или Yandex GPT). "
            "Тесты из Cursor/другой страны могут давать 200, а с VPS — 403."
        )
    return base


def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        text = str(m.get("text") or "")
        if role == "system":
            if text.strip():
                system_parts.append(text)
            continue
        if role in ("user", "assistant"):
            out.append({"role": role, "content": text})
    system = "\n\n".join(system_parts)
    return system, out


class AnthropicClaudeProvider(PromptedLLMMixin, LLMProvider):
    prompt_namespace = "anthropic_claude"

    def __init__(self, settings: Settings | None = None, *, prompt_store: PromptStore | None = None):
        self.settings = settings or get_settings()
        self.prompts = prompt_store

    @property
    def configured(self) -> bool:
        return self.settings.anthropic_configured

    def _model_name(self, model: AnswerModel = "lite") -> str:
        if model == "pro":
            return self.settings.anthropic_model_pro
        return self.settings.anthropic_model_lite

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _http_client(self, *, timeout: float) -> httpx.AsyncClient:
        proxy = (self.settings.anthropic_http_proxy or "").strip()
        if proxy:
            return httpx.AsyncClient(timeout=timeout, proxy=proxy)
        return httpx.AsyncClient(timeout=timeout)

    async def _build_messages_from_fact_pack(
        self,
        query: str,
        sources: list[SearchSource],
        fact_pack: FactPack,
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        intent_howto: bool = False,
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = (
                f"\n\nПодсказка: в выдаче может не хватать данных. "
                f"В конце ответа задай уточнение: {hint_clarify}"
            )
        slots = fact_pack.fact_slots or []
        synthesis = uses_synthesis_grounding(slots, intent_howto=intent_howto)
        if strict_facts and not synthesis:
            strict_block = strict_answer_addon()
        elif synthesis:
            strict_block = answer_addon_for_slots(slots, synthesis=True)
        else:
            strict_block = ""
        facts_block = format_fact_pack_for_prompt(
            fact_pack,
            sources,
            fact_slots=slots,
            intent_howto=intent_howto,
        )
        user_content = f"""{facts_block}
{_format_history(history)}{extra}{clarify_block}{strict_block}

Вопрос: {query}"""
        system = await self.get_prompt("answer_search", ANSWER_SEARCH)
        return [
            {"role": "system", "text": system},
            {"role": "user", "text": user_content},
        ]

    async def _build_messages_search(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
        intent_howto: bool = False,
    ) -> list[dict]:
        if fact_pack is not None:
            return await self._build_messages_from_fact_pack(
                query,
                sources,
                fact_pack,
                history,
                prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                intent_howto=intent_howto,
            )
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = f"\n\nПодсказка: в выдаче может не хватать данных. В конце ответа задай уточнение: {hint_clarify}"
        strict_block = strict_answer_addon() if strict_facts else ""
        user_content = f"""Источники:
{_format_sources(sources)}
{_format_history(history)}{extra}{clarify_block}{strict_block}

Вопрос: {query}"""
        system = await self.get_prompt("answer_search", ANSWER_SEARCH)
        return [
            {"role": "system", "text": system},
            {"role": "user", "text": user_content},
        ]

    async def _build_messages_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        user_content = f"""{_format_history(history)}{extra}

Вопрос: {query}"""
        if _query_has_document_block(query):
            system = await self.get_prompt("answer_document", ANSWER_DOCUMENT)
        elif is_meta_assistant_query(query):
            system = await self.get_prompt("answer_meta", ANSWER_META)
        else:
            system = await self.get_prompt("answer_direct", ANSWER_DIRECT)
        return [
            {"role": "system", "text": system},
            {"role": "user", "text": user_content},
        ]

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        if not self.configured:
            return '{"needs_search": true, "search_query": "mock", "answer_model": "lite", "reason": "mock"}'

        system, msg_list = _to_anthropic_messages(messages)
        payload: dict = {
            "model": self._model_name(model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": msg_list,
        }
        if system:
            payload["system"] = system

        try:
            async with self._http_client(timeout=90.0) as client:
                response = await client.post(MESSAGES_URL, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            model = self._model_name(model)
            logger.error("Claude HTTP %s (%s): %s", e.response.status_code, model, e.response.text[:500])
            raise YandexServiceError(
                "gpt",
                _anthropic_http_error_message(e.response, model=model),
                e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            logger.exception("Claude request failed")
            raise YandexServiceError("gpt", "Claude недоступен (сеть)") from e

        parts: list[str] = []
        for block in data.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)

    async def _stream_messages(
        self,
        messages: list[dict],
        *,
        model: AnswerModel,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        system, msg_list = _to_anthropic_messages(messages)
        payload: dict = {
            "model": self._model_name(model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": msg_list,
        }
        if system:
            payload["system"] = system

        def _delta_text(event: dict) -> str | None:
            et = event.get("type")
            if et == "error":
                err = event.get("error") or {}
                msg = err.get("message") or str(err)
                raise YandexServiceError("gpt", f"Claude stream: {msg}")
            if et == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") in (None, "text_delta"):
                    text = delta.get("text")
                    if text:
                        return str(text)
            if et == "message_delta":
                delta = event.get("delta") or {}
                text = delta.get("text")
                if text:
                    return str(text)
            return None

        try:
            async with self._http_client(timeout=120.0) as client:
                async with client.stream(
                    "POST", MESSAGES_URL, headers=self._headers(), json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        model_name = self._model_name(model)
                        logger.error("Claude stream HTTP %s (%s): %s", response.status_code, model_name, body)
                        req = httpx.Request("POST", MESSAGES_URL)
                        resp = httpx.Response(response.status_code, request=req, content=body.encode())
                        raise YandexServiceError(
                            "gpt",
                            _anthropic_http_error_message(resp, model=model_name),
                            response.status_code,
                        )
                    yielded = False
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
                        text = _delta_text(event)
                        if text:
                            yielded = True
                            yield text
                    if not yielded:
                        logger.warning("Claude stream returned no text deltas (model=%s)", payload.get("model"))
        except httpx.HTTPStatusError as e:
            model_name = self._model_name(model)
            logger.error("Claude stream HTTP %s (%s): %s", e.response.status_code, model_name, e.response.text[:500])
            raise YandexServiceError(
                "gpt",
                _anthropic_http_error_message(e.response, model=model_name),
                e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            logger.exception("Claude stream failed")
            raise YandexServiceError("gpt", "Claude недоступен (сеть)") from e

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
        if not self.configured:
            mock = "Ответ в режиме mock (задайте ANTHROPIC_API_KEY). [1]"
            async for part in _yield_text_paced(mock):
                yield part
            return

        max_tokens = 4500 if model == "pro" else 2800
        messages = await self._build_messages_search(
            query,
            sources,
            history,
            prior_sources_block,
            hint_clarify=hint_clarify,
            strict_facts=strict_facts,
            fact_pack=fact_pack,
            intent_howto=intent_howto,
        )
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.35 if model == "pro" else 0.3,
        ):
            yield chunk

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Ответ по контексту (mock Claude)."):
                yield part
            return

        messages = await self._build_messages_direct(query, history, prior_sources_block)
        max_tokens = 2500 if model == "pro" else 1500
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
        ):
            yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        from app.services.yandex_gpt import _default_follow_up_suggestions, _normalize_follow_up_suggestions

        if not self.configured:
            return _default_follow_up_suggestions(query)

        follow_system = await self.get_prompt("follow_ups_system", FOLLOW_UPS_SYSTEM)
        messages = [
            {"role": "system", "text": follow_system},
            {"role": "user", "text": f"Запрос: {query}\n\nОтвет: {answer[:2000]}"},
        ]
        try:
            text = await self.complete_text(messages, model="lite", max_tokens=320, temperature=0.4)
        except Exception:
            logger.exception("Claude follow-ups failed")
            return _default_follow_up_suggestions(query)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return _normalize_follow_up_suggestions([str(x) for x in items[:3]])
            except json.JSONDecodeError:
                pass
        return _default_follow_up_suggestions(query)
