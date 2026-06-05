"""Генерация изображений через встроенную функцию GigaChat text2image."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

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
    match = _FILE_ID_IN_IMG_RE.search(text or "")
    return match.group(1) if match else None


def _clean_assistant_text(raw: str) -> str:
    """Убирает тег <img … fuse=\"true\"/> и лишние разделители из ответа GigaChat."""
    text = _IMG_TAG_RE.sub("", raw or "")
    text = re.sub(r'fuse\s*=\s*["\']true["\']\s*/>', "", text, flags=re.I)
    text = re.sub(r"<img[^>]*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s\-—–:]+", "", text).strip()
    return text


def _delta_from_chunk(data: dict) -> tuple[str, str, str]:
    choices = data.get("choices") or []
    if not choices:
        return "", "", ""
    delta = choices[0].get("delta") or {}
    role = str(delta.get("role") or "")
    content = str(delta.get("content") or "")
    name = str(delta.get("name") or "")
    return role, content, name


async def stream_gigachat_image_generation(
    prompt: str,
    *,
    settings: Settings | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """
    Yields (event_type, message).
    event_type: status | done | error
    """
    settings = settings or get_settings()
    if not settings.gigachat_configured:
        yield ("error", "GigaChat не настроен")
        return

    model = settings.gigachat_model_pro
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "function_call": "auto",
        "functions": [{"name": "text2image"}],
        "stream": True,
    }

    content_parts: list[str] = []
    file_id: str | None = None

    try:
        async for data in iter_chat_completion_chunks(payload, settings=settings):
            role, content, name = _delta_from_chunk(data)
            if role == "function_in_progress" and name == "text2image" and content:
                yield ("status", content.strip())
                continue
            if content:
                content_parts.append(content)
                found = _extract_file_id(content)
                if found:
                    file_id = found
    except Exception as exc:
        logger.exception("GigaChat image stream failed")
        if _is_gigachat_pro_payment_error(exc):
            yield ("error", "Лимит GigaChat Pro исчерпан. Попробуйте позже.")
            return
        try:
            raise _gigachat_service_error(exc) from exc
        except Exception as e:
            yield ("error", str(e))
            return

    full_text = "".join(content_parts).strip()
    if not file_id:
        file_id = _extract_file_id(full_text)

    if not file_id:
        # Fallback: non-stream request
        try:
            full_text = await chat_completion_text(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "function_call": "auto",
                    "functions": [{"name": "text2image"}],
                },
                settings=settings,
            )
            file_id = _extract_file_id(full_text)
        except Exception as exc:
            logger.exception("GigaChat image fallback failed")
            yield ("error", str(_gigachat_service_error(exc)))
            return

    if not file_id:
        yield ("error", "Не удалось получить изображение от GigaChat")
        return

    try:
        image_bytes = await download_file_bytes(file_id, settings=settings)
    except Exception as exc:
        logger.exception("GigaChat image download failed")
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
            last_status = payload
        elif event_type == "error":
            raise ImageGenerationError("generation_failed", payload)
        elif event_type == "image_bytes":
            image_bytes = payload
        elif event_type == "done":
            lines = payload.split("\n", 1)
            file_id = lines[0].strip()
            text = lines[1].strip() if len(lines) > 1 else ""
            if not isinstance(image_bytes, bytes) or not is_valid_image_bytes(image_bytes):
                image_bytes = await download_file_bytes(file_id, settings=settings)
            if not is_valid_image_bytes(image_bytes):
                raise ImageGenerationError("generation_failed", "GigaChat вернул повреждённое изображение")
            return ImageGenerationResult(
                image_bytes=image_bytes,
                assistant_text=text or "Готово — изображение сгенерировано.",
                gigachat_file_id=file_id,
            )
    raise ImageGenerationError("generation_failed", last_status or "Нет ответа от GigaChat")
