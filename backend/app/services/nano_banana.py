"""Google Gemini Nano Banana 2 — image generation via Interactions API."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import httpx

from app.services.gigachat_image_gen import ImageGenerationError

logger = logging.getLogger(__name__)

_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_MODEL = "gemini-3.1-flash-image"
_TIMEOUT = 90.0


@dataclass
class NanaBananaResult:
    image_bytes: bytes
    mime_type: str  # "image/png" or "image/jpeg"
    assistant_text: str


async def generate_nano_banana_image(
    prompt: str,
    *,
    api_key: str,
    model: str = _MODEL,
) -> NanaBananaResult:
    """
    Generate an image via Google Gemini Nano Banana 2 (Interactions API).
    Returns image bytes as PNG/JPEG.
    """
    if not api_key:
        raise ImageGenerationError("provider_unavailable", "GOOGLE_API_KEY не настроен")

    payload = {
        "model": model,
        "input": [{"type": "text", "text": prompt}],
    }

    logger.info("NanaBanana: generating image model=%s prompt_len=%d", model, len(prompt))

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
        body = response.text[:300]
        logger.warning("NanaBanana API error %d: %s", response.status_code, body)
        raise ImageGenerationError(
            "api_error",
            f"Nano Banana API вернул ошибку {response.status_code}",
        )

    try:
        data = response.json()
        # Interactions API returns the Interaction object at the TOP LEVEL (not nested).
        # convenience property `output_image` holds the last image block.
        # Fallback: scan steps[].content[] for type="image" blocks.

        # Check for async "in_progress" status — shouldn't happen for sync requests
        # but handle gracefully
        if data.get("status") == "in_progress":
            logger.warning("NanaBanana: in_progress response (unexpected for sync call)")
            raise ImageGenerationError("empty_response", "Nano Banana не завершил генерацию")

        img_b64 = ""
        mime_type = "image/png"
        assistant_text = ""

        # Primary: top-level output_image (convenience property)
        output_image = data.get("output_image") or {}
        img_b64 = str(output_image.get("data") or "")
        mime_type = str(output_image.get("mime_type") or output_image.get("mimeType") or "image/png")

        # Fallback: scan steps → content blocks
        if not img_b64:
            for step in (data.get("steps") or []):
                content_list = step.get("content") or step.get("model_output", {}).get("content") or []
                for block in content_list:
                    if str(block.get("type") or "").lower() == "image":
                        img_b64 = str(block.get("data") or "")
                        mime_type = str(block.get("mime_type") or block.get("mimeType") or "image/png")
                        break
                if img_b64:
                    break

        if not img_b64:
            logger.warning("NanaBanana: no image in response: %s", str(data)[:400])
            raise ImageGenerationError("empty_response", "Nano Banana не вернул изображение")

        # Collect text output from top-level output_text or steps
        assistant_text = str(data.get("output_text") or "").strip()
        if not assistant_text:
            for step in (data.get("steps") or []):
                for block in (step.get("content") or []):
                    if str(block.get("type") or "").lower() == "text":
                        assistant_text = str(block.get("text") or "").strip()
                        break
                if assistant_text:
                    break

        image_bytes = base64.b64decode(img_b64)
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
