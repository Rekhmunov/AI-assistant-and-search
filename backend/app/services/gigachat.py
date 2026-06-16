"""GigaChat API (Сбер) — текст и vision через files API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from app.core.config import Settings, get_settings
from app.services.attachment_bundle import VisionImage
from app.services.gigachat_client import (
    chat_completion_text,
    iter_chat_stream,
    upload_file_bytes,
)
from app.services.answer_guard import direct_system_addons, search_answer_addon
from app.services.facts.format import format_fact_pack_for_prompt
from app.services.facts.models import FactPack
from app.services.llm_prompted import PromptedLLMMixin
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.prompts.defaults import (
    ANSWER_DIRECT,
    ANSWER_DOCUMENT,
    ANSWER_META,
    ANSWER_SEARCH,
    ANSWER_VISION,
    FOLLOW_UPS_SYSTEM,
)
from app.services.prompts.gigachat_defaults import GIGACHAT_VISION_SEARCH_SUMMARY
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


def _gigachat_service_error(exc: Exception) -> YandexServiceError:
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 402:
            return YandexServiceError(
                "gpt",
                "GigaChat: закончился лимит или требуется оплата (402). "
                "Пополните баланс в кабинете GigaChat или временно переключите LLM на Yandex GPT в админке.",
                status_code=402,
            )
        if code == 401:
            return YandexServiceError(
                "gpt",
                "GigaChat: ошибка авторизации (401). Проверьте GIGACHAT_CREDENTIALS в .env.",
                status_code=401,
            )
        if code == 429:
            return YandexServiceError(
                "gpt",
                "GigaChat: слишком много запросов (429). Попробуйте через минуту.",
                status_code=429,
            )
        return YandexServiceError(
            "gpt",
            f"GigaChat HTTP {code}: {exc.response.text[:200]}",
            status_code=code,
        )
    return YandexServiceError("gpt", f"GigaChat недоступен: {exc}")


def _is_gigachat_pro_payment_error(exc: Exception) -> bool:
    import httpx

    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 402


def _to_gigachat_messages(messages: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            text = str(m.get("text") or m.get("content") or "").strip()
            if text:
                out.append({"role": "system", "content": text})
        elif role == "user":
            if m.get("attachments"):
                out.append(
                    {
                        "role": "user",
                        "content": str(m.get("content") or m.get("text") or " ").strip() or " ",
                        "attachments": list(m["attachments"]),
                    }
                )
            else:
                text = str(m.get("text") or m.get("content") or "").strip()
                if text:
                    out.append({"role": "user", "content": text})
        elif role == "assistant":
            text = str(m.get("text") or m.get("content") or "").strip()
            if text:
                out.append({"role": "assistant", "content": text})
    return out


def _ensure_gigachat_payload(messages: list[dict]) -> list[dict[str, Any]]:
    converted = _to_gigachat_messages(messages)
    if not converted:
        raise YandexServiceError(
            "gpt",
            "GigaChat: пустой запрос (проверьте system/user промпты в админке)",
        )
    if not any(m.get("role") == "user" for m in converted):
        raise YandexServiceError(
            "gpt",
            "GigaChat: нет user-сообщения (проверьте шаблон промпта)",
        )
    return converted


class GigaChatProvider(PromptedLLMMixin, LLMProvider):
    prompt_namespace = "gigachat"

    def __init__(self, settings: Settings | None = None, *, prompt_store: PromptStore | None = None):
        self.settings = settings or get_settings()
        self.prompts = prompt_store

    @property
    def configured(self) -> bool:
        return self.settings.gigachat_configured

    def _model_name(self, model: AnswerModel = "lite") -> str:
        if model == "pro":
            return self.settings.gigachat_model_pro
        return self.settings.gigachat_model_lite

    async def _upload_vision_images(self, vision_images: list[VisionImage]) -> list[str]:
        ids: list[str] = []
        for img in vision_images[:10]:
            import base64

            raw = base64.standard_b64decode(img.data_base64)
            fid = await upload_file_bytes(raw, img.filename, settings=self.settings)
            ids.append(fid)
        return ids

    def _vision_messages(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        *,
        file_ids: list[str],
        system: str,
        prior_sources_block: str = "",
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        user_text = f"""{_format_history(history)}{extra}

{query}"""
        messages: list[dict] = [{"role": "system", "text": system}]
        if len(file_ids) == 1:
            messages.append(
                {
                    "role": "user",
                    "content": user_text,
                    "attachments": [file_ids[0]],
                }
            )
        else:
            for i, fid in enumerate(file_ids):
                messages.append(
                    {
                        "role": "user",
                        "content": f"Изображение {i + 1}",
                        "attachments": [fid],
                    }
                )
            messages.append({"role": "user", "content": user_text})
        return messages

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        if not self.configured:
            return '{"needs_search": true, "search_query": "mock", "answer_model": "lite", "reason": "mock"}'
        payload = {
            "model": self._model_name(model),
            "messages": _ensure_gigachat_payload(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            return await chat_completion_text(payload, settings=self.settings)
        except Exception as e:
            if model == "pro" and _is_gigachat_pro_payment_error(e):
                logger.warning("GigaChat Pro 402 — fallback to lite for complete_text")
                payload["model"] = self._model_name("lite")
                try:
                    return await chat_completion_text(payload, settings=self.settings)
                except Exception as retry_exc:
                    logger.exception("GigaChat complete_text lite fallback failed")
                    raise _gigachat_service_error(retry_exc) from retry_exc
            logger.exception("GigaChat complete_text failed")
            raise _gigachat_service_error(e) from e

    async def _stream_messages(
        self,
        messages: list[dict],
        *,
        model: AnswerModel,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Ответ GigaChat (mock)."):
                yield part
            return
        payload: dict[str, Any] = {
            "model": self._model_name(model),
            "messages": _ensure_gigachat_payload(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async for chunk in iter_chat_stream(payload, settings=self.settings):
                yield chunk
        except Exception as e:
            if model == "pro" and _is_gigachat_pro_payment_error(e):
                logger.warning("GigaChat Pro 402 — fallback to lite for stream")
                payload["model"] = self._model_name("lite")
                if payload["max_tokens"] > 2200:
                    payload["max_tokens"] = 2200
                try:
                    async for chunk in iter_chat_stream(payload, settings=self.settings):
                        yield chunk
                    return
                except Exception as retry_exc:
                    logger.exception("GigaChat stream lite fallback failed")
                    raise _gigachat_service_error(retry_exc) from retry_exc
            logger.exception("GigaChat stream failed")
            raise _gigachat_service_error(e) from e

    async def summarize_vision_for_search(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        *,
        prior_sources_block: str = "",
    ) -> str:
        if not self.configured:
            return "Mock: на фото объект для поиска."
        file_ids = await self._upload_vision_images(vision_images)
        system = GIGACHAT_VISION_SEARCH_SUMMARY
        messages = self._vision_messages(
            query,
            vision_images,
            history,
            file_ids=file_ids,
            system=system,
            prior_sources_block=prior_sources_block,
        )
        payload = {
            "model": self._model_name("lite"),
            "messages": _to_gigachat_messages(messages),
            "max_tokens": 900,
            "temperature": 0.2,
        }
        try:
            return await chat_completion_text(payload, settings=self.settings)
        except Exception as e:
            logger.exception("GigaChat vision summary failed")
            raise _gigachat_service_error(e) from e

    async def stream_answer_vision(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        model: AnswerModel = "pro",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Анализ фото (mock GigaChat)."):
                yield part
            return
        file_ids = await self._upload_vision_images(vision_images)
        system = await self.get_prompt("answer_vision", ANSWER_VISION)
        messages = self._vision_messages(
            query,
            vision_images,
            history,
            file_ids=file_ids,
            system=system,
            prior_sources_block=prior_sources_block,
        )
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.35,
        ):
            yield chunk

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
            async for part in _yield_text_paced("Ответ GigaChat (mock). [1]"):
                yield part
            return
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
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
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
            async for part in _yield_text_paced("Ответ по контексту (mock GigaChat)."):
                yield part
            return
        messages = await self._build_messages_direct(query, history, prior_sources_block)
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            messages,
            model=model,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        if not self.configured:
            return []
        system = await self.get_prompt("follow_ups_system", FOLLOW_UPS_SYSTEM)
        user = f"Запрос: {query}\n\nОтвет:\n{answer[:4000]}"
        payload = {
            "model": self._model_name("lite"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 200,
            "temperature": 0.4,
        }
        try:
            raw = await chat_completion_text(payload, settings=self.settings)
        except Exception:
            logger.exception("GigaChat follow-ups failed")
            return []
        import json
        import re

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        # Сначала пробуем найти JSON-массив в тексте (GigaChat может добавлять текст вокруг)
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list) and all(isinstance(x, str) for x in data):
                    return [x.strip() for x in data if x.strip()][:5]
            except json.JSONDecodeError:
                pass

        # Fallback: прямой json.loads
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                # Если список содержит строки — возвращаем
                flat: list[str] = []
                for x in data:
                    if isinstance(x, str):
                        flat.append(x.strip())
                    elif isinstance(x, list):
                        # Вложенный список — разворачиваем
                        flat.extend(str(s).strip() for s in x if str(s).strip())
                return [s for s in flat if s][:5]
        except json.JSONDecodeError:
            pass

        # Fallback: разбивка по строкам
        lines = [q.strip() for q in raw.split("\n") if q.strip() and not q.strip().startswith("[")]
        return [l for l in lines if len(l) > 5][:5]
