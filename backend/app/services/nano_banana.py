"""Google Gemini Nano Banana 2 — image generation via Interactions API.

IMPORTANT: Since June 8, 2026 the Interactions API requires an explicit
  response_format: {"type": "image"}
in the request body.  Without it the model responds with text only and
no image is produced.

Reference: https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import httpx

from app.services.gigachat_image_gen import ImageGenerationError

logger = logging.getLogger(__name__)

_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_MODEL    = "gemini-3.1-flash-image"   # дефолт — 1K, быстрый, дешёвый
_MODEL_HQ = "gemini-3-pro-image"       # high_quality — 2K/4K, дороже
_TIMEOUT = 90.0


@dataclass
class NanaBananaResult:
    image_bytes: bytes
    mime_type: str  # "image/png" or "image/jpeg"
    assistant_text: str


def _detect_image_mime(img_bytes: bytes) -> str:
    if img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(img_bytes) >= 12 and img_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _safe_b64decode(s: str) -> bytes:
    """Decode base64 robustly:
    - strips whitespace / newlines
    - strips data-URI prefix (data:image/...;base64,)
    - tries standard base64 first, falls back to URL-safe (-_)
    - adds missing padding automatically
    """
    s = s.strip()
    # Strip data-URI prefix if present
    if s.startswith("data:"):
        s = s.split(",", 1)[-1].strip()
    # Normalise padding
    pad = (4 - len(s) % 4) % 4
    s_padded = s + "=" * pad
    try:
        return base64.b64decode(s_padded, validate=True)
    except Exception:
        # Fall back to URL-safe alphabet (-_)
        return base64.urlsafe_b64decode(s_padded)


def _extract_image_from_response(data: dict) -> tuple[str, str]:
    """
    Return (base64_data, mime_type) from any known Gemini response shape.

    Tried in order:
    1. output_image  — Interactions API convenience property
    2. steps[].content[] type=image  — Interactions API steps schema
    3. candidates[].content.parts[].inlineData  — generateContent format
    """
    # 1. Top-level convenience property (Interactions API)
    output_image = data.get("output_image") or {}
    img_b64 = str(output_image.get("data") or "")
    mime = str(output_image.get("mime_type") or output_image.get("mimeType") or "image/jpeg")
    if img_b64:
        return img_b64, mime

    # 2. steps[].content[] type=image  (Interactions API new schema)
    for step in (data.get("steps") or []):
        content_list = step.get("content") or []
        for block in content_list:
            if str(block.get("type") or "").lower() == "image":
                img_b64 = str(block.get("data") or "")
                mime = str(block.get("mime_type") or block.get("mimeType") or "image/jpeg")
                if img_b64:
                    return img_b64, mime

    # 3. candidates[].content.parts[].inlineData  (generateContent format)
    for candidate in (data.get("candidates") or []):
        for part in (candidate.get("content", {}).get("parts") or []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            img_b64 = str(inline.get("data") or "")
            mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/jpeg")
            if img_b64:
                return img_b64, mime

    return "", "image/jpeg"


import re as _re

# Gemini interleaved-output placeholders that reference generated images inline.
# Strip them so plain text descriptions don't contain "{image}" or similar.
_IMAGE_PLACEHOLDER_RE = _re.compile(
    r"\{image\d*\}|\[image\d*\]|\[изображение\d*\]|\{img\d*\}",
    _re.IGNORECASE,
)


def _strip_image_placeholders(text: str) -> str:
    cleaned = _IMAGE_PLACEHOLDER_RE.sub("", text)
    # Collapse multiple blank lines left by removed placeholders
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_text_from_response(data: dict) -> str:
    """Collect assistant text from any known Gemini response shape."""
    text = str(data.get("output_text") or "").strip()
    if text:
        return _strip_image_placeholders(text)

    # steps schema — collect text blocks from ALL model_output steps
    parts: list[str] = []
    for step in (data.get("steps") or []):
        for block in (step.get("content") or []):
            if str(block.get("type") or "").lower() == "text":
                t = str(block.get("text") or "").strip()
                if t:
                    parts.append(t)
    if parts:
        return _strip_image_placeholders(" ".join(parts))

    # candidates schema
    for candidate in (data.get("candidates") or []):
        for part in (candidate.get("content", {}).get("parts") or []):
            if "text" in part and part["text"]:
                return _strip_image_placeholders(str(part["text"]).strip())

    return ""


async def _generate_nano_banana_once(
    prompt: str,
    *,
    api_key: str,
    model: str,
    input_images: list[bytes] | None,
    image_size: str = "1K",
) -> NanaBananaResult:
    """Single attempt at image generation (no retry logic here)."""
    if not api_key:
        raise ImageGenerationError("provider_unavailable", "GOOGLE_API_KEY не настроен")

    input_items: list[dict] = []
    if input_images:
        for img_bytes in input_images:
            img_b64 = base64.b64encode(img_bytes).decode("ascii")
            mime = _detect_image_mime(img_bytes)
            input_items.append({"type": "image", "data": img_b64, "mime_type": mime})
    input_items.append({"type": "text", "text": prompt})

    # gemini-3.1-flash-image не поддерживает image_size и при его передаче
    # возвращает текст вместо изображения.
    # Для 2K автоматически переключаемся на gemini-3-pro-image.
    response_format: dict = {
        "type": "image",
        "mime_type": "image/jpeg",
    }
    if image_size and image_size != "1K":
        model = _MODEL_HQ
        response_format["image_size"] = image_size

    payload = {
        "model": model,
        "input": input_items,
        "response_format": response_format,
    }

    from app.core.config import get_settings as _get_settings
    _settings = _get_settings()
    _proxy = (_settings.google_http_proxy or "").strip() or None

    mode = "compose" if len(input_images or []) > 1 else ("edit" if input_images else "generate")
    logger.info(
        "NanaBanana: %s model=%s prompt_len=%d n_input_images=%d proxy=%s",
        mode, model, len(prompt), len(input_images or []), bool(_proxy),
    )

    try:
        _client_kwargs: dict = {"timeout": _TIMEOUT}
        if _proxy:
            _client_kwargs["proxy"] = _proxy
        async with httpx.AsyncClient(**_client_kwargs) as client:
            response = await client.post(
                _API_URL,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.warning("NanaBanana HTTP error: %s", exc)
        raise ImageGenerationError("network_error", f"Nano Banana недоступен: {exc}") from exc

    if response.status_code == 401:
        raise ImageGenerationError("auth_error", "Неверный GOOGLE_API_KEY")
    if response.status_code == 429:
        raise ImageGenerationError("rate_limit", "Превышен лимит запросов Nano Banana")
    if not response.is_success:
        body = response.text[:400]
        logger.warning("NanaBanana API error %d: %s", response.status_code, body)
        # Специальная обработка: Gemini блокирует генерацию реальных людей и unsafe-контент
        if response.status_code == 400 and (
            "Image generation blocked" in body
            or "blocked for unspecified reasons" in body
            or "Unable to show the generated image" in body
        ):
            raise ImageGenerationError(
                "content_blocked",
                "Генерация заблокирована: модель не может создать это изображение. "
                "Возможные причины: изображение реального человека, защищённый контент или нарушение правил использования. "
                "Попробуйте изменить описание.",
            )
        raise ImageGenerationError(
            "api_error",
            f"Nano Banana API вернул ошибку {response.status_code}: {body[:120]}",
        )

    try:
        data = response.json()

        if data.get("status") == "in_progress":
            logger.warning("NanaBanana: in_progress response (unexpected for sync call)")
            raise ImageGenerationError("empty_response", "Nano Banana не завершил генерацию")

        img_b64, mime_type = _extract_image_from_response(data)

        if not img_b64:
            logger.warning(
                "NanaBanana: no image found in response (status=%s keys=%s body=%.600s)",
                data.get("status"),
                list(data.keys()),
                str(data),
            )
            raise ImageGenerationError("empty_response", "Nano Banana не вернул изображение")

        assistant_text = _extract_text_from_response(data)

        image_bytes = _safe_b64decode(img_b64)
        actual_mime = _detect_image_mime(image_bytes)
        if actual_mime != mime_type:
            logger.info("NanaBanana: actual mime %s differs from declared %s — using actual", actual_mime, mime_type)
            mime_type = actual_mime
        logger.info("NanaBanana: success %d bytes mime=%s", len(image_bytes), mime_type)
        return NanaBananaResult(
            image_bytes=image_bytes,
            mime_type=mime_type,
            assistant_text=assistant_text,
        )
    except (KeyError, ValueError) as exc:
        logger.warning("NanaBanana: response parse error: %s", exc)
        raise ImageGenerationError("parse_error", "Не удалось обработать ответ Nano Banana") from exc
    except base64.binascii.Error as exc:
        logger.warning("NanaBanana: base64 decode error: %s", exc)
        raise ImageGenerationError("parse_error", "Не удалось декодировать изображение") from exc


async def generate_nano_banana_image(
    prompt: str,
    *,
    api_key: str,
    model: str = _MODEL,
    input_images: list[bytes] | None = None,
    image_size: str = "1K",
) -> NanaBananaResult:
    """
    Generate or edit an image via Google Gemini Nano Banana 2 Interactions API.

    input_images: if provided, each image is prepended before the text prompt.
      - 1 image + prompt → img2img editing (recolor, style transfer, element removal)
      - 2+ images + prompt → image composition (combine photos)

    Automatically retries once when the API returns a 200 response but with no
    image data (empty_response).  Transient model-side refusals are the most
    common cause of empty responses; a single retry resolves them in practice.
    """
    for attempt in range(2):
        try:
            return await _generate_nano_banana_once(
                prompt,
                api_key=api_key,
                model=model,
                input_images=input_images,
                image_size=image_size,
            )
        except ImageGenerationError as exc:
            # Only retry on empty_response — other errors are deterministic
            if exc.code != "empty_response" or attempt >= 1:
                raise
            logger.warning("NanaBanana: empty_response on attempt %d, retrying…", attempt + 1)
    # Unreachable: the loop always raises on attempt=1; satisfy type checker
    raise ImageGenerationError("empty_response", "Nano Banana не вернул изображение")
