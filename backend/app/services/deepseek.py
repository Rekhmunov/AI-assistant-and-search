"""DeepSeek API (OpenAI-совместимый) — тот же пайплайн Glosix, другой LLM."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.answer_guard import direct_system_addons, search_answer_addon, strict_answer_addon
from app.services.facts.format import format_fact_pack_for_prompt
from app.services.facts.models import FactPack
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


def _deepseek_http_error_message(response: httpx.Response, *, model: str) -> str:
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

    base = f"DeepSeek недоступен (HTTP {response.status_code})"
    if model:
        base += f", модель {model}"
    if detail:
        base += f": {detail}"
    return base


def _to_openai_messages(messages: list[dict]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        text = str(m.get("text") or "").strip()
        if role in ("system", "user", "assistant") and text:
            out.append({"role": str(role), "content": text})
    return out


class DeepSeekProvider(PromptedLLMMixin, LLMProvider):
    prompt_namespace = "deepseek"

    def __init__(self, settings: Settings | None = None, *, prompt_store: PromptStore | None = None):
        self.settings = settings or get_settings()
        self.prompts = prompt_store

    @property
    def configured(self) -> bool:
        return self.settings.deepseek_configured

    def _model_name(self, model: AnswerModel = "lite") -> str:
        if model == "pro":
            return self.settings.deepseek_model_pro
        return self.settings.deepseek_model_lite

    def _chat_url(self) -> str:
        base = (self.settings.deepseek_base_url or "https://api.deepseek.com").rstrip("/")
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def _http_client(self, *, timeout: float) -> httpx.AsyncClient:
        proxy = (self.settings.deepseek_http_proxy or "").strip()
        if proxy:
            return httpx.AsyncClient(timeout=timeout, proxy=proxy)
        return httpx.AsyncClient(timeout=timeout)

    def _thinking_payload(
        self,
        model: AnswerModel,
        *,
        max_tokens: int,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Thinking на pro только для длинных non-stream запросов (иначе пустой content)."""
        if model != "pro" or stream or max_tokens < 256:
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}

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
        grounding_mode: str = "strict",
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = (
                f"\n\nПодсказка: в выдаче может не хватать данных. "
                f"В конце ответа задай уточнение: {hint_clarify}"
            )
        slots = fact_pack.fact_slots or []
        strict_block = search_answer_addon(
            grounding=grounding_mode,
            strict_facts=strict_facts,
            fact_slots=slots,
            intent_howto=intent_howto,
        )
        facts_block = format_fact_pack_for_prompt(
            fact_pack,
            sources,
            fact_slots=slots,
            intent_howto=intent_howto,
            grounding=grounding_mode,  # type: ignore[arg-type]
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
        grounding_mode: str = "strict",
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
                grounding_mode=grounding_mode,
            )
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = f"\n\nПодсказка: в выдаче может не хватать данных. В конце ответа задай уточнение: {hint_clarify}"
        strict_block = search_answer_addon(
            grounding=grounding_mode,
            strict_facts=strict_facts,
        )
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
        system += direct_system_addons(query)
        return [
            {"role": "system", "text": system},
            {"role": "user", "text": user_content},
        ]

    def _text_from_completion(self, data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "").strip()
        if content:
            return content
        return str(msg.get("reasoning_content") or "").strip()

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        if not self.configured:
            return '{"needs_search": true, "search_query": "mock", "answer_model": "lite", "reason": "mock"}'

        model_id = self._model_name(model)
        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": _to_openai_messages(messages),
            **self._thinking_payload(model, max_tokens=max_tokens),
        }
        if model == "lite":
            payload["temperature"] = temperature

        try:
            async with self._http_client(timeout=90.0) as client:
                response = await client.post(self._chat_url(), headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("DeepSeek HTTP %s (%s): %s", e.response.status_code, model_id, e.response.text[:500])
            raise YandexServiceError(
                "gpt",
                _deepseek_http_error_message(e.response, model=model_id),
                e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            logger.exception("DeepSeek request failed")
            raise YandexServiceError("gpt", "DeepSeek недоступен (сеть)") from e

        return self._text_from_completion(data)

    async def _stream_completion(
        self,
        messages: list[dict],
        *,
        model: AnswerModel,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        model_id = self._model_name(model)
        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": _to_openai_messages(messages),
            **self._thinking_payload(model, max_tokens=max_tokens, stream=True),
        }
        if model == "lite":
            payload["temperature"] = temperature

        try:
            async with self._http_client(timeout=120.0) as client:
                async with client.stream(
                    "POST", self._chat_url(), headers=self._headers(), json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        logger.error("DeepSeek stream HTTP %s (%s): %s", response.status_code, model_id, body)
                        req = httpx.Request("POST", self._chat_url())
                        resp = httpx.Response(response.status_code, request=req, content=body.encode())
                        raise YandexServiceError(
                            "gpt",
                            _deepseek_http_error_message(resp, model=model_id),
                            response.status_code,
                        )
                    yielded = False
                    _accumulated = ""
                    logger.warning("DEEPSEEK_FIX_V2 streaming started model=%s", model_id)
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
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            if text == _accumulated:
                                logger.warning("DEEPSEEK_FIX_V2 skipped duplicate chunk len=%d", len(text))
                                continue
                            _accumulated += text
                            yielded = True
                            yield str(text)
                    if not yielded:
                        logger.warning("DeepSeek stream returned no content (model=%s)", model_id)
        except httpx.HTTPStatusError as e:
            logger.error("DeepSeek stream HTTP %s (%s): %s", e.response.status_code, model_id, e.response.text[:500])
            raise YandexServiceError(
                "gpt",
                _deepseek_http_error_message(e.response, model=model_id),
                e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            logger.exception("DeepSeek stream failed")
            raise YandexServiceError("gpt", "DeepSeek недоступен (сеть)") from e

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
        if not self.configured:
            mock = "Ответ в режиме mock (задайте DEEPSEEK_API_KEY). [1]"
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
            grounding_mode=grounding_mode,
        )
        async for chunk in self._stream_completion(
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
        logger.warning("DEEPSEEK_DIRECT_ENTRY model=%s query=%r configured=%s", model, (query or "")[:30], self.configured)
        if not self.configured:
            async for part in _yield_text_paced("Ответ по контексту (mock DeepSeek)."):
                yield part
            return

        messages = await self._build_messages_direct(query, history, prior_sources_block)
        max_tokens = 2500 if model == "pro" else 1500
        use_pro = model == "pro"
        async for chunk in self._stream_completion(
            messages,
            model="pro" if use_pro else "lite",
            max_tokens=max_tokens,
            temperature=0.4,
        ):
            yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        from app.services.yandex_gpt import (
            _default_follow_up_suggestions,
            _finalize_follow_up_suggestions,
            _normalize_follow_up_suggestions,
        )

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
            logger.exception("DeepSeek follow-ups failed")
            return _default_follow_up_suggestions(query)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return _finalize_follow_up_suggestions([str(x) for x in items], query)
            except json.JSONDecodeError:
                pass
        return _default_follow_up_suggestions(query)
