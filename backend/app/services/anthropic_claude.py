"""Claude (Anthropic API) — тот же пайплайн Glosix, другой LLM."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.answer_guard import direct_system_addons, search_answer_addon, strict_answer_addon
from app.services.facts.format import format_fact_pack_for_prompt
from app.services.facts.models import FactPack
from app.services.llm_prompted import PromptedLLMMixin
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.attachment_bundle import VisionImage
from app.services.prompts.defaults import (
    ANSWER_DIRECT,
    ANSWER_DOCUMENT,
    ANSWER_META,
    ANSWER_SEARCH,
    ANSWER_VISION,
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


def _extract_source_from_tool_result_item(item: dict, index: int) -> dict | None:
    """
    Извлекает источник из одного элемента tool_result контента.
    Anthropic возвращает документы в формате:
      {"type": "document", "document": {"url": "...", "title": "...", "snippet": "..."}}
    или
      {"type": "web_search_result", "url": "...", "title": "...", "snippet": "..."}
    """
    if not isinstance(item, dict):
        return None

    itype = item.get("type", "")

    # Формат document
    if itype == "document":
        doc = item.get("document") or {}
        url = doc.get("url") or doc.get("source") or ""
        title = doc.get("title") or ""
        snippet = doc.get("encrypted_snippet") or doc.get("snippet") or ""
        if url:
            return {"url": url, "title": title or url, "snippet": snippet, "index": index}

    # Формат web_search_result (более ранние версии)
    if itype in {"web_search_result", "search_result"}:
        url = item.get("url") or ""
        title = item.get("title") or ""
        snippet = item.get("snippet") or item.get("content") or ""
        if url:
            return {"url": url, "title": title or url, "snippet": snippet, "index": index}

    # Плоский формат с url на верхнем уровне
    url = item.get("url") or ""
    if url:
        return {
            "url": url,
            "title": item.get("title") or url,
            "snippet": item.get("snippet") or item.get("content") or "",
            "index": index,
        }

    return None
API_VERSION = "2023-06-01"

# Инструменты Claude Pro: веб-поиск, загрузка URL, выполнение кода
_PRO_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
    {"type": "code_execution_20260120", "name": "code_execution"},
]

# Claude Search: max_uses=1 ограничивает один поисковый раунд — убирает 5-10с задержки
# при повторных поисках. web_fetch без лимита чтобы прочитать нужные страницы.
_CLAUDE_SEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 1},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
    {"type": "code_execution_20260120", "name": "code_execution"},
]
# Beta-заголовки: динамическая фильтрация поиска + prompt caching
_PRO_BETA_HEADERS = "code-execution-web-tools-2026-02-09,prompt-caching-2024-07-31"
_LITE_BETA_HEADERS = "prompt-caching-2024-07-31"


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
            raw_content = m.get("content")
            if isinstance(raw_content, list):
                out.append({"role": role, "content": raw_content})
            elif text.strip():
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

    def _headers(self, *, model: AnswerModel = "lite") -> dict[str, str]:
        beta = _PRO_BETA_HEADERS if model == "pro" else _LITE_BETA_HEADERS
        return {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
            "anthropic-beta": beta,
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
        # Prompt caching для системного промпта
        if system:
            payload["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        try:
            async with self._http_client(timeout=90.0) as client:
                response = await client.post(MESSAGES_URL, headers=self._headers(model=model), json=payload)
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
        enable_tools: bool = False,
    ) -> AsyncIterator[str]:
        """
        enable_tools=True — добавляет _PRO_TOOLS (web_search, web_fetch, code_execution).
        По умолчанию False: Yandex RAG не нуждается в инструментах Claude,
        их добавление замедляет ответ (Claude делает лишние round-trips).
        """
        system, msg_list = _to_anthropic_messages(messages)
        payload: dict = {
            "model": self._model_name(model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": msg_list,
        }
        # Prompt caching: системный промпт кешируется — экономия 90% токенов при повторных запросах
        if system:
            payload["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        # Инструменты только когда явно запрошены (Claude Search, code_execution и т.п.)
        if enable_tools and model == "pro":
            payload["tools"] = _PRO_TOOLS

        def _delta_text(event: dict) -> str | None:
            et = event.get("type")
            if et == "error":
                err = event.get("error") or {}
                msg = err.get("message") or str(err)
                raise YandexServiceError("gpt", f"Claude stream: {msg}")
            if et == "content_block_delta":
                delta = event.get("delta") or {}
                # Берём текстовые блоки; tool_use/input_json_delta — пропускаем
                if delta.get("type") == "text_delta":
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
            async with self._http_client(timeout=180.0) as client:
                async with client.stream(
                    "POST", MESSAGES_URL, headers=self._headers(model=model), json=payload
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
        grounding_mode: str = "strict",
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
            grounding_mode=grounding_mode,
        )
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.35 if model == "pro" else 0.3,
        ):
            yield chunk

    async def stream_answer_vision(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        model: AnswerModel = "pro",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Анализ фото (mock Claude)."):
                yield part
            return

        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        user_text = f"""{_format_history(history)}{extra}

{query}"""

        content_blocks: list[dict] = []
        for img in vision_images[:10]:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.media_type,
                        "data": img.data_base64,
                    },
                }
            )
        content_blocks.append({"type": "text", "text": user_text})

        system = await self.get_prompt("answer_vision", ANSWER_VISION)
        messages = [
            {"role": "system", "text": system},
            {"role": "user", "content": content_blocks},
        ]
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.35,
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

    async def stream_search_with_claude_sources(
        self,
        query: str,
        history: list[tuple[str, str]],
        *,
        model: AnswerModel = "pro",
    ):
        """
        Режим Claude Search: поиск и ответ только через Claude web_search.
        Yields tuples: ("text", str) | ("source", dict) | ("done", None).

        source dict: {"url": str, "title": str, "snippet": str, "index": int}
        """
        if not self.configured:
            yield ("text", "Claude недоступен (mock). Задайте ANTHROPIC_API_KEY.")
            yield ("done", None)
            return

        from app.services.prompts.anthropic_claude_defaults import ANTHROPIC_CLAUDE_SEARCH_PROMPT

        history_text = ""
        for role, text in history[-6:]:
            prefix = "Пользователь" if role == "user" else "Ассистент"
            history_text += f"{prefix}: {text}\n\n"

        user_content = f"{history_text}Вопрос: {query}".strip()

        payload: dict = {
            "model": self._model_name(model),
            "max_tokens": 5000,
            "temperature": 0.3,
            "stream": True,
            "system": ANTHROPIC_CLAUDE_SEARCH_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
            "tools": _CLAUDE_SEARCH_TOOLS,
        }

        sources: list[dict] = []
        source_index = 0

        try:
            async with self._http_client(timeout=180.0) as client:
                async with client.stream(
                    "POST", MESSAGES_URL,
                    headers=self._headers(model="pro"),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise YandexServiceError(
                            "gpt",
                            _anthropic_http_error_message(
                                httpx.Response(response.status_code, request=httpx.Request("POST", MESSAGES_URL), content=body.encode()),
                                model=self._model_name(model),
                            ),
                            response.status_code,
                        )

                    # Парсим стрим: собираем текст и источники из web_search
                    current_block_type: str = ""
                    # Накапливаем JSON дельты для tool_result
                    _tool_result_json_buf: str = ""

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

                        et = event.get("type")

                        if et == "error":
                            err = (event.get("error") or {}).get("message", "unknown")
                            raise YandexServiceError("gpt", f"Claude Search stream: {err}")

                        if et == "content_block_start":
                            block = event.get("content_block") or {}
                            btype = block.get("type", "")
                            current_block_type = btype
                            _tool_result_json_buf = ""

                            # Вариант А: tool_result с inline content (старый формат)
                            if btype in {"tool_result", "web_search_tool_result"}:
                                content = block.get("content") or []
                                for item in content:
                                    src = _extract_source_from_tool_result_item(item, source_index + 1)
                                    if src:
                                        source_index += 1
                                        sources.append(src)
                                        yield ("source", src)
                            # Вариант Б: server_tool_use с inline результатами
                            elif btype == "server_tool_use":
                                inp = block.get("input") or {}
                                results = inp.get("results") or inp.get("content") or []
                                if isinstance(results, list):
                                    for item in results:
                                        src = _extract_source_from_tool_result_item(item, source_index + 1)
                                        if src:
                                            source_index += 1
                                            sources.append(src)
                                            yield ("source", src)

                        elif et == "content_block_delta":
                            delta = event.get("delta") or {}
                            dtype = delta.get("type", "")

                            if dtype == "text_delta" and current_block_type == "text":
                                text = delta.get("text", "")
                                if text:
                                    yield ("text", text)

                            elif dtype in {"input_json_delta", "partial_json"}:
                                # Накапливаем JSON дельты — может содержать search results
                                _tool_result_json_buf += delta.get("partial_json", "") or delta.get("input_json", "")

                        elif et == "content_block_stop":
                            # Пробуем распарсить накопленный JSON если это tool_result
                            if _tool_result_json_buf and current_block_type in {
                                "tool_result", "web_search_tool_result", "server_tool_use"
                            }:
                                try:
                                    parsed = json.loads(_tool_result_json_buf)
                                    results = parsed if isinstance(parsed, list) else (
                                        parsed.get("results") or parsed.get("content") or []
                                    )
                                    for item in (results if isinstance(results, list) else []):
                                        src = _extract_source_from_tool_result_item(item, source_index + 1)
                                        if src:
                                            source_index += 1
                                            sources.append(src)
                                            yield ("source", src)
                                except (json.JSONDecodeError, Exception):
                                    pass
                            _tool_result_json_buf = ""
                            current_block_type = ""

                        # Обработка специальных событий для server-side tools Anthropic
                        elif et == "tool_use":
                            # Некоторые версии API возвращают tool_use как top-level event
                            inp = event.get("input") or {}
                            results = inp.get("results") or []
                            for item in (results if isinstance(results, list) else []):
                                src = _extract_source_from_tool_result_item(item, source_index + 1)
                                if src:
                                    source_index += 1
                                    sources.append(src)
                                    yield ("source", src)

        except httpx.HTTPError as exc:
            raise YandexServiceError("gpt", f"Claude Search недоступен (сеть): {exc}") from exc

        yield ("done", None)

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
            logger.exception("Claude follow-ups failed")
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
