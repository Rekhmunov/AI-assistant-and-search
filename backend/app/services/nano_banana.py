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
        interaction = data.get("interaction") or {}
        output_image = interaction.get("output_image") or {}
        img_b64 = output_image.get("data") or ""
        mime_type = output_image.get("mimeType") or "image/png"
        assistant_text = ""
        # Also collect text output if any
        for block in interaction.get("output", []):
            if block.get("type") == "text":
                assistant_text = str(block.get("text") or "")
                break

        if not img_b64:
            logger.warning("NanaBanana: no output_image in response: %s", str(data)[:300])
            raise ImageGenerationError("empty_response", "Nano Banana не вернул изображение")

        image_bytes = base64.b64decode(img_b64)
        logger.info("NanaBanana: success %d bytes mime=%s", len(image_bytes), mime_type)
        return NanaBananaResult(
            image_bytes=image_bytes,
            mime_type=mime_type,
            assistant_text=assistant_text,
        )
    except (KeyError, ValueError, base64.binascii.Error) as exc:
        logger.warning("NanaBanana: response parse error: %s", exc)
        raise ImageGenerationError("parse_error", "Не удалось обработать ответ Nano Banana") from exc
