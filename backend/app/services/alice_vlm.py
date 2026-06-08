"""Yandex AI Studio vision: Alice AI VLM (когда появится в API) или Gemma 3 27B."""

from __future__ import annotations

import base64
import io
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


def _extract_yandex_api_error(payload: dict) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        for key in ("message", "detail", "code", "type"):
            val = str(err.get(key) or "").strip()
            if val:
                return val
    elif isinstance(err, str) and err.strip():
        return err.strip()
    for key in ("message", "detail", "title"):
        val = str(payload.get(key) or "").strip()
        if val and val not in ("Bad Request",):
            return val
    resp = payload.get("response")
    if isinstance(resp, dict):
        nested = _extract_yandex_api_error(resp)
        if nested:
            return nested
    return ""


def encode_vision_image_for_yandex(
    data_base64: str,
    *,
    max_side: int = 1536,
    max_bytes: int = 900_000,
) -> str:
    """Сжимает фото для Gemma API (большие iPhone JPEG ломают stream с error)."""
    from PIL import Image

    raw = base64.standard_b64decode(data_base64)
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    quality = 85
    buf = io.BytesIO()
    while quality >= 50:
        buf.seek(0)
        buf.truncate()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= max_bytes:
            break
        quality -= 10
    encoded = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


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
    if detail == "Failed to get model":
        msg += ". Модель aliceai-vlm пока не в каталоге API; пробуем gemma-3-27b-it."
    elif response.status_code == 403:
        msg += (
            ". Проверьте scope API-ключа yc.ai.languageModels.execute "
            "и доступ к gemma-3-27b-it в Model Gallery AI Studio."
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

    def _responses_url(self) -> str:
        base = self.settings.yandex_ai_studio_base_url.rstrip("/")
        return f"{base}/responses"

    def _model_uri_candidates(self) -> list[str]:
        folder = self.settings.yandex_folder_id.strip()
        if not folder:
            return []
        configured = self.settings.yandex_alice_vlm_model.strip()
        gemma = self.settings.yandex_vision_gemma_model.strip()
        gemma_suffixes: list[str] = []
        for suffix in (gemma, "gemma-3-27b-it", "gemma-3-27b-it/latest"):
            if suffix and suffix not in gemma_suffixes:
                gemma_suffixes.append(suffix)
        alice_suffixes: list[str] = []
        if self.settings.yandex_vision_alice_first:
            for suffix in (configured, "aliceai-vlm/latest", "aliceai-vlm"):
                if suffix and suffix not in alice_suffixes and suffix not in gemma_suffixes:
                    alice_suffixes.append(suffix)
            order = (*alice_suffixes, *gemma_suffixes)
        else:
            order = tuple(gemma_suffixes)
        return [f"gpt://{folder}/{suffix}" for suffix in order]

    @staticmethod
    def _is_gemma_model(model_uri: str) -> bool:
        return "gemma-3-27b-it" in model_uri

    def _log_vision_success(self, model_uri: str, *, stream: bool) -> None:
        action = "stream" if stream else "complete"
        if self._is_gemma_model(model_uri):
            logger.info(
                "Yandex vision %s via gemma model_uri=%s (aliceai-vlm not in API catalog)",
                action,
                model_uri,
            )
            return
        logger.info("Alice VLM %s success model_uri=%s", action, model_uri)

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.yandex_api_key.strip()
        headers = {
            "Authorization": f"Api-Key {api_key}",
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

    def _vision_input(
        self,
        query: str,
        vision_images: list[VisionImage],
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
    ) -> list[dict[str, Any]]:
        """Responses API: input_image + input_text (не image_url/text из Chat Completions)."""
        user_text = self._vision_user_text(query, history, prior_sources_block)
        content: list[dict[str, Any]] = []
        for img in vision_images[:10]:
            image_url = encode_vision_image_for_yandex(
                img.data_base64,
                max_side=self.settings.yandex_vision_image_max_side,
                max_bytes=self.settings.yandex_vision_image_max_bytes,
            )
            content.append({"type": "input_image", "image_url": image_url})
        content.append({"type": "input_text", "text": user_text})
        return [{"role": "user", "content": content}]

    @staticmethod
    def _text_from_response(data: dict) -> str:
        status = str(data.get("status") or "").lower()
        if status in ("failed", "cancelled", "incomplete"):
            detail = _extract_yandex_api_error(data)
            msg = f"Yandex vision failed ({status})"
            if detail:
                msg += f": {detail}"
            raise YandexServiceError("gpt", msg)
        parts: list[str] = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for block in item.get("content") or []:
                if block.get("type") == "output_text":
                    parts.append(str(block.get("text") or ""))
        if not parts and data.get("output_text"):
            parts.append(str(data["output_text"]))
        return "".join(parts).strip()

    @staticmethod
    def _text_from_stream_event(event: dict) -> str:
        event_type = str(event.get("type") or "")
        if event_type == "response.output_text.delta":
            return str(event.get("delta") or "")
        if event_type == "response.output_text.done":
            return str(event.get("text") or "")
        if event_type == "response.completed":
            return AliceVLMProvider._text_from_response(event.get("response") or {})
        if event_type in ("error", "response.failed", "response.error"):
            detail = _extract_yandex_api_error(event)
            if not detail and event_type == "response.failed":
                detail = _extract_yandex_api_error(event.get("response") or {})
            if detail:
                raise YandexServiceError("gpt", f"Yandex vision stream: {detail}")
            raise YandexServiceError("gpt", f"Yandex vision stream error ({event_type})")
        return ""

    def _build_payload(
        self,
        *,
        model_uri: str,
        instructions: str,
        input_messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_uri,
            "instructions": instructions,
            "input": input_messages,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if stream:
            payload["stream"] = True
        return payload

    async def _complete_for_model(
        self,
        instructions: str,
        input_messages: list[dict[str, Any]],
        model_uri: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        url = self._responses_url()
        payload = self._build_payload(
            model_uri=model_uri,
            instructions=instructions,
            input_messages=input_messages,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        text = self._text_from_response(data)
        if not text:
            raise YandexServiceError("gpt", "Alice AI VLM вернула пустой ответ")
        return text

    async def _complete_messages(
        self,
        instructions: str,
        input_messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        candidates = self._model_uri_candidates()
        if not candidates:
            raise YandexServiceError("gpt", "Alice AI VLM: не задан YANDEX_FOLDER_ID")

        last_error: Exception | None = None
        for model_uri in candidates:
            try:
                text = await self._complete_for_model(
                    instructions,
                    input_messages,
                    model_uri,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self._log_vision_success(model_uri, stream=False)
                return text
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Yandex vision HTTP %s model_uri=%s: %s",
                    e.response.status_code,
                    model_uri,
                    e.response.text[:500],
                )
                last_error = _alice_vlm_http_error(e.response)
                if self._retryable_model_status(e.response.status_code):
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                logger.exception("Yandex vision request failed model_uri=%s", model_uri)
                raise YandexServiceError("gpt", "Alice AI VLM недоступен (сеть)") from e
            except YandexServiceError as e:
                logger.warning("Yandex vision empty/declined model_uri=%s: %s", model_uri, e)
                last_error = e
                continue

        if last_error:
            raise last_error
        raise YandexServiceError("gpt", "Alice AI VLM недоступен")

    async def _stream_messages_for_model(
        self,
        instructions: str,
        input_messages: list[dict[str, Any]],
        model_uri: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        url = self._responses_url()
        payload = self._build_payload(
            model_uri=model_uri,
            instructions=instructions,
            input_messages=input_messages,
            max_output_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    logger.warning(
                        "Yandex vision stream HTTP %s model_uri=%s: %s",
                        response.status_code,
                        model_uri,
                        body,
                    )
                    req = httpx.Request("POST", url)
                    resp = httpx.Response(response.status_code, request=req, content=body.encode())
                    raise _alice_vlm_http_error(resp)

                yielded = False
                event_types: list[str] = []
                last_error_event: dict | None = None
                pending_event_type = ""
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        pending_event_type = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                    elif line.startswith("{"):
                        raw = line
                    else:
                        continue
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if pending_event_type and not event.get("type"):
                        event["type"] = pending_event_type
                        pending_event_type = ""
                    event_type = str(event.get("type") or "")
                    if event_type and (not event_types or event_types[-1] != event_type):
                        event_types.append(event_type)
                    if event_type in ("error", "response.failed", "response.error"):
                        last_error_event = event
                    try:
                        text = self._text_from_stream_event(event)
                    except YandexServiceError:
                        raise
                    if text:
                        yielded = True
                        yield text

                if not yielded:
                    if last_error_event:
                        detail = _extract_yandex_api_error(last_error_event)
                        if not detail and last_error_event.get("response"):
                            detail = _extract_yandex_api_error(last_error_event["response"])
                        logger.warning(
                            "Yandex vision stream error model_uri=%s events=%s detail=%s raw=%s",
                            model_uri,
                            event_types[:12],
                            detail,
                            json.dumps(last_error_event, ensure_ascii=False)[:400],
                        )
                        if detail:
                            raise YandexServiceError("gpt", f"Yandex vision stream: {detail}")
                    logger.warning(
                        "Yandex vision empty stream model_uri=%s events=%s",
                        model_uri,
                        event_types[:12],
                    )

    async def _stream_messages(
        self,
        instructions: str,
        input_messages: list[dict[str, Any]],
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
                streamed_parts: list[str] = []
                async for chunk in self._stream_messages_for_model(
                    instructions,
                    input_messages,
                    model_uri,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    streamed_parts.append(chunk)
                    yield chunk
                if streamed_parts:
                    self._log_vision_success(model_uri, stream=True)
                    return

                # Стрим пустой — пробуем синхронный ответ той же модели.
                logger.info("Yandex vision sync fallback model_uri=%s", model_uri)
                text = await self._complete_for_model(
                    instructions,
                    input_messages,
                    model_uri,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                async for chunk in _yield_text_paced(text):
                    yield chunk
                self._log_vision_success(model_uri, stream=True)
                return
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Yandex vision stream HTTP %s model_uri=%s: %s",
                    e.response.status_code,
                    model_uri,
                    e.response.text[:500],
                )
                last_error = _alice_vlm_http_error(e.response)
                if self._retryable_model_status(e.response.status_code):
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                logger.exception("Yandex vision stream failed model_uri=%s", model_uri)
                raise YandexServiceError("gpt", "Alice AI VLM недоступен (сеть)") from e
            except YandexServiceError as e:
                logger.warning("Yandex vision failed model_uri=%s: %s", model_uri, e)
                last_error = e
                continue

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
        input_messages = self._vision_input(query, vision_images, history, prior_sources_block)
        return await self._complete_messages(
            ALICE_VLM_VISION_SEARCH_SUMMARY,
            input_messages,
            max_tokens=900,
            temperature=0.2,
        )

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
        input_messages = self._vision_input(query, vision_images, history, prior_sources_block)
        max_tokens = 3500 if model == "pro" else 2200
        async for chunk in self._stream_messages(
            system,
            input_messages,
            max_tokens=max_tokens,
            temperature=0.35,
        ):
            yield chunk
