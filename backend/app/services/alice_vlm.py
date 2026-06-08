"""Alice AI VLM (Yandex Cloud) — vision через OpenAI-совместимый chat API."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.attachment_bundle import VisionImage
from app.services.llm_prompted import PromptedLLMMixin
from app.services.prompts.alice_vlm_defaults import (
    ALICE_VLM_ANSWER_VISION,
    ALICE_VLM_VISION_SEARCH_SUMMARY,
)
from app.services.prompts.store import PromptStore
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import _format_history, _yield_text_paced

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]
CHAT_URL = "https://llm.api.cloud.yandex.net/v1/chat/completions"


def _alice_vlm_http_error(response: httpx.Response) -> YandexServiceError:
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

    msg = f"Alice AI VLM недоступен (HTTP {response.status_code})"
    if detail:
        msg += f": {detail}"
    if response.status_code == 403:
        msg += (
            ". Проверьте роль ai.languageModels.user у сервисного аккаунта "
            "и доступ к модели aliceai-vlm в AI Studio."
        )
    return YandexServiceError("gpt", msg, response.status_code)


class AliceVLMProvider(PromptedLLMMixin):
    prompt_namespace = "alice_vlm"

    def __init__(self, settings: Settings | None = None, *, prompt_store: PromptStore | None = None):
        self.settings = settings or get_settings()
        self.prompts = prompt_store

    @property
    def configured(self) -> bool:
        return self.settings.yandex_configured

    def _model_uri_candidates(self) -> list[str]:
        folder = self.settings.yandex_folder_id.strip()
        if not folder:
            return []
        configured = self.settings.yandex_alice_vlm_model.strip()
        suffixes: list[str] = []
        for suffix in (configured, "aliceai-vlm/latest", "aliceai-vlm"):
            if suffix and suffix not in suffixes:
                suffixes.append(suffix)
        return [f"gpt://{folder}/{suffix}" for suffix in suffixes]

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.yandex_api_key.strip()
        headers = {
            # OpenAI-совместимый /v1/chat/completions ожидает Bearer (не Api-Key).
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-data-logging-enabled": "false",
        }
        folder = self.settings.yandex_folder_id.strip()
        if folder:
            headers["x-folder-id"] = folder
        return headers

    @staticmethod
    def _retryable_model_status(status_code: int) -> bool:
        return status_code in (400, 404, 422)

    def _vision_user_text(
        self,
        query: str,
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
    ) -> str:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        return f"""{_format_history(history)}{extra}

{query}"""

    def _vision_messages(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        *,
        system: str,
        prior_sources_block: str = "",
    ) -> list[dict[str, Any]]:
        user_text = self._vision_user_text(query, history, prior_sources_block)
        content: list[dict[str, Any]] = []
        for img in vision_images[:10]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.media_type};base64,{img.data_base64}",
                    },
                }
            )
        content.append({"type": "text", "text": user_text})
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

    def _text_from_completion(self, data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        finish = str(choice.get("finish_reason") or "").lower()
        if finish == "content_filter":
            raise YandexServiceError(
                "gpt",
                "Alice AI VLM отклонила запрос (content_filter)",
            )
        msg = choice.get("message") or {}
        return str(msg.get("content") or "").strip()

    async def _complete_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        candidates = self._model_uri_candidates()
        if not candidates:
            raise YandexServiceError("gpt", "Alice AI VLM: не задан YANDEX_FOLDER_ID")

        last_error: Exception | None = None
        for model_uri in candidates:
            payload = {
                "model": model_uri,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(CHAT_URL, headers=self._headers(), json=payload)
                    response.raise_for_status()
                    data = response.json()
                text = self._text_from_completion(data)
                if not text:
                    raise YandexServiceError("gpt", "Alice AI VLM вернула пустой ответ")
                logger.info("Alice VLM complete success model_uri=%s", model_uri)
                return text
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Alice VLM HTTP %s model_uri=%s: %s",
                    e.response.status_code,
                    model_uri,
                    e.response.text[:500],
                )
                last_error = _alice_vlm_http_error(e.response)
                if self._retryable_model_status(e.response.status_code):
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                logger.exception("Alice VLM request failed model_uri=%s", model_uri)
                raise YandexServiceError("gpt", "Alice AI VLM недоступен (сеть)") from e
            except YandexServiceError as e:
                last_error = e
                continue

        if last_error:
            raise last_error
        raise YandexServiceError("gpt", "Alice AI VLM недоступен")

    async def _stream_messages_for_model(
        self,
        messages: list[dict[str, Any]],
        model_uri: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model_uri,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", CHAT_URL, headers=self._headers(), json=payload
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    logger.warning(
                        "Alice VLM stream HTTP %s model_uri=%s: %s",
                        response.status_code,
                        model_uri,
                        body,
                    )
                    req = httpx.Request("POST", CHAT_URL)
                    resp = httpx.Response(response.status_code, request=req, content=body.encode())
                    raise _alice_vlm_http_error(resp)

                yielded = False
                content_filter = False
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
                    choice = choices[0]
                    finish = str(choice.get("finish_reason") or "").lower()
                    if finish == "content_filter":
                        content_filter = True
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yielded = True
                        yield str(text)

                if content_filter and not yielded:
                    raise YandexServiceError(
                        "gpt",
                        "Alice AI VLM отклонила запрос (content_filter)",
                    )
                if not yielded:
                    raise YandexServiceError("gpt", "Alice AI VLM вернула пустой ответ")

    async def _stream_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        candidates = self._model_uri_candidates()
        if not candidates:
            raise YandexServiceError("gpt", "Alice AI VLM: не задан YANDEX_FOLDER_ID")

        last_error: Exception | None = None
        for model_uri in candidates:
            try:
                async for chunk in self._stream_messages_for_model(
                    messages,
                    model_uri,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    yield chunk
                logger.info("Alice VLM stream success model_uri=%s", model_uri)
                return
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Alice VLM stream HTTP %s model_uri=%s: %s",
                    e.response.status_code,
                    model_uri,
                    e.response.text[:500],
                )
                last_error = _alice_vlm_http_error(e.response)
                if self._retryable_model_status(e.response.status_code):
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                logger.exception("Alice VLM stream failed model_uri=%s", model_uri)
                raise YandexServiceError("gpt", "Alice AI VLM недоступен (сеть)") from e
            except YandexServiceError as e:
                last_error = e
                if e.status_code and self._retryable_model_status(e.status_code):
                    continue
                raise

        if last_error:
            raise last_error
        raise YandexServiceError("gpt", "Alice AI VLM недоступен")

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
        messages = self._vision_messages(
            query,
            vision_images,
            history,
            system=ALICE_VLM_VISION_SEARCH_SUMMARY,
            prior_sources_block=prior_sources_block,
        )
        return await self._complete_messages(messages, max_tokens=900, temperature=0.2)

    async def stream_answer_vision(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        model: AnswerModel = "pro",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.configured:
            async for part in _yield_text_paced("Анализ фото (mock Alice VLM)."):
                yield part
            return

        system = await self.get_prompt("answer_vision", ALICE_VLM_ANSWER_VISION)
        messages = self._vision_messages(
            query,
            vision_images,
            history,
            system=system,
            prior_sources_block=prior_sources_block,
        )
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            messages,
            max_tokens=max_tokens,
            temperature=0.35,
        ):
            yield chunk
