"""Генерация изображений через встроенную функцию GigaChat text2image."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.gigachat import _gigachat_service_error, _is_gigachat_pro_payment_error
from app.services.gigachat_client import (
    chat_completion_text,
    download_file_bytes,
    iter_chat_completion_chunks,
)
from app.services.image_bytes import detect_image_mime, is_valid_image_bytes

logger = logging.getLogger(__name__)

_GIGACHAT_FILE_ID = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
# GigaChat: <img src="uuid" fuse="true"/> — атрибуты в любом порядке
_IMG_TAG_RE = re.compile(rf"<img\s+[^>]*/?>", re.I)
_FILE_ID_IN_IMG_RE = re.compile(
    rf'src=["\']({_GIGACHAT_FILE_ID})["\']',
    re.I,
)
_BARE_FILE_ID_RE = re.compile(rf"\b({_GIGACHAT_FILE_ID})\b", re.I)


class ImageGenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ImageGenerationResult:
    image_bytes: bytes
    assistant_text: str
    gigachat_file_id: str


def _extract_file_id(text: str) -> str | None:
    raw = text or ""
    match = _FILE_ID_IN_IMG_RE.search(raw)
    if match:
        return match.group(1)
    bare = _BARE_FILE_ID_RE.search(raw)
    return bare.group(1) if bare else None


def _clean_assistant_text(raw: str) -> str:
    """Убирает тег <img … fuse=\"true\"/> и лишние разделители из ответа GigaChat."""
    text = _IMG_TAG_RE.sub("", raw or "")
    text = re.sub(r'fuse\s*=\s*["\']true["\']\s*/>', "", text, flags=re.I)
    text = re.sub(r"<img[^>]*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s\-—–:]+", "", text).strip()
    return text


def _image_gen_payload(prompt: str, model: str, *, stream: bool) -> dict[str, Any]:
    """Запрос как в доке GigaChat: function_call=auto без лишних полей."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "function_call": "auto",
        "stream": stream,
    }


def _content_from_chunk(data: dict) -> tuple[str, str, str]:
    choices = data.get("choices") or []
    if not choices:
        return "", "", ""
    choice = choices[0]
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    role = str(delta.get("role") or message.get("role") or "")
    content = str(delta.get("content") or message.get("content") or "")
    name = str(delta.get("name") or "")
    return role, content, name


def _models_for_image_gen(settings: Settings) -> list[str]:
    pro = (settings.gigachat_model_pro or "").strip()
    lite = (settings.gigachat_model_lite or "").strip()
    models: list[str] = []
    if pro:
        models.append(pro)
    if lite and lite not in models:
        models.append(lite)
    return models


async def _completion_with_models(
    prompt: str,
    *,
    settings: Settings,
    stream: bool,
) -> tuple[str, str]:
    """Возвращает (model_used, full_text). Пробует pro, затем lite при 402."""
    last_exc: Exception | None = None
    for model in _models_for_image_gen(settings):
        try:
            if stream:
                parts: list[str] = []
                payload = _image_gen_payload(prompt, model, stream=True)
                async for data in iter_chat_completion_chunks(payload, settings=settings):
                    role, content, name = _content_from_chunk(data)
                    if role == "function_in_progress" and name == "text2image" and content:
                        parts.append(content)
                        continue
                    if content:
                        parts.append(content)
                return model, "".join(parts).strip()
            text = await chat_completion_text(
                _image_gen_payload(prompt, model, stream=False),
                settings=settings,
            )
            return model, text
        except Exception as exc:
            last_exc = exc
            if _is_gigachat_pro_payment_error(exc) and model == settings.gigachat_model_pro.strip():
                logger.warning("GigaChat image: pro 402, trying lite model")
                continue
            raise
    if last_exc:
        raise last_exc
    return "", ""


async def stream_gigachat_image_generation(
    prompt: str,
    *,
    settings: Settings | None = None,
) -> AsyncIterator[tuple[str, str | bytes]]:
    """
    Yields (event_type, message).
    event_type: status | image_bytes | done | error
    """
    settings = settings or get_settings()
    if not settings.gigachat_configured:
        yield ("error", "GigaChat не настроен")
        return

    yield ("status", "Запускаем генерацию…")

    full_text = ""
    model_used = ""
    try:
        model_used, full_text = await _completion_with_models(
            prompt,
            settings=settings,
            stream=False,
        )
    except Exception as exc:
        logger.exception("GigaChat image completion failed")
        if _is_gigachat_pro_payment_error(exc):
            yield ("error", "Лимит GigaChat Pro исчерпан. Попробуйте позже.")
            return
        try:
            raise _gigachat_service_error(exc) from exc
        except Exception as e:
            yield ("error", str(e))
            return

    file_id = _extract_file_id(full_text)

    if not file_id:
        yield ("status", "Повторяем запрос…")
        try:
            model_used, stream_text = await _completion_with_models(
                prompt,
                settings=settings,
                stream=True,
            )
            if stream_text:
                full_text = stream_text
            file_id = _extract_file_id(full_text)
        except Exception as exc:
            logger.exception("GigaChat image stream retry failed")
            if not _is_gigachat_pro_payment_error(exc):
                try:
                    raise _gigachat_service_error(exc) from exc
                except Exception as e:
                    yield ("error", str(e))
                    return

    if not file_id:
        logger.warning(
            "GigaChat image: no file_id model=%s prompt=%r response=%r",
            model_used,
            prompt[:120],
            (full_text or "")[:500],
        )
        yield ("error", "Не удалось получить изображение от GigaChat")
        return

    try:
        image_bytes = await download_file_bytes(file_id, settings=settings)
    except Exception as exc:
        logger.exception("GigaChat image download failed file_id=%s", file_id)
        yield ("error", "Не удалось скачать сгенерированное изображение")
        return

    if not is_valid_image_bytes(image_bytes):
        mime_hint = detect_image_mime(image_bytes) or "unknown"
        logger.warning(
            "GigaChat image invalid: file_id=%s size=%d mime=%s head=%s",
            file_id,
            len(image_bytes),
            mime_hint,
            image_bytes[:16].hex() if image_bytes else "",
        )
        yield ("error", "GigaChat вернул повреждённое изображение")
        return

    clean_text = _clean_assistant_text(full_text)
    yield ("image_bytes", image_bytes)
    yield ("done", f"{file_id}\n{clean_text}")


async def generate_gigachat_image(prompt: str, *, settings: Settings | None = None) -> ImageGenerationResult:
    last_status = ""
    image_bytes: bytes | None = None
    async for event_type, payload in stream_gigachat_image_generation(prompt, settings=settings):
        if event_type == "status":
            last_status = str(payload)
        elif event_type == "error":
            raise ImageGenerationError("generation_failed", str(payload))
        elif event_type == "image_bytes" and isinstance(payload, bytes):
            image_bytes = payload
        elif event_type == "done":
            lines = str(payload).split("\n", 1)
            file_id = lines[0].strip()
            text = lines[1].strip() if len(lines) > 1 else ""
            if not isinstance(image_bytes, bytes) or not is_valid_image_bytes(image_bytes):
                image_bytes = await download_file_bytes(file_id, settings=settings or get_settings())
            if not is_valid_image_bytes(image_bytes):
                raise ImageGenerationError("generation_failed", "GigaChat вернул повреждённое изображение")
            return ImageGenerationResult(
                image_bytes=image_bytes,
                assistant_text=text or "Готово — изображение сгенерировано.",
                gigachat_file_id=file_id,
            )
    raise ImageGenerationError("generation_failed", last_status or "Нет ответа от GigaChat")
