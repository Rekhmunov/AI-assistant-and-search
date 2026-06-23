"""Извлечение и загрузка изображений и голосовых сообщений из MAX."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.services.attachment_bundle import VisionImage
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_IMAGE_TYPES = frozenset({"image", "photo"})
_VOICE_TYPES = frozenset({"audio_msg", "voice", "audio"})


def _message_obj(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    return message if isinstance(message, dict) else None


def message_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    message = _message_obj(payload)
    if not message:
        return []
    body = message.get("body")
    if isinstance(body, dict):
        raw = body.get("attachments")
        if isinstance(raw, list):
            return [a for a in raw if isinstance(a, dict)]
    raw = message.get("attachments")
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    return []


def _attachment_urls(att: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    payload = att.get("payload")
    if isinstance(payload, dict):
        for key in ("url", "photo_url", "preview_url", "src", "base_url"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw.startswith("http"):
                urls.append(raw)
        for key in ("photos", "variants"):
            variants = payload.get(key)
            if isinstance(variants, list):
                for item in variants:
                    if isinstance(item, dict):
                        u = item.get("url")
                        if isinstance(u, str) and u.startswith("http"):
                            urls.append(u)
    return urls


def message_has_images(payload: dict[str, Any]) -> bool:
    for att in message_attachments(payload):
        att_type = str(att.get("type") or "").lower()
        if att_type in _IMAGE_TYPES:
            return True
    return False


def extract_voice_url(payload: dict[str, Any]) -> str | None:
    """Возвращает URL голосового сообщения или None если его нет."""
    for att in message_attachments(payload):
        att_type = str(att.get("type") or "").lower()
        if att_type not in _VOICE_TYPES:
            continue
        att_payload = att.get("payload")
        if not isinstance(att_payload, dict):
            continue
        for key in ("url", "link", "download_url"):
            url = att_payload.get(key)
            if isinstance(url, str) and url.startswith("http"):
                return url
    return None


async def transcribe_voice_message(
    payload: dict[str, Any],
    *,
    bot: MaxBotService | None = None,
) -> str | None:
    """
    Если в payload есть голосовое сообщение — скачивает и транскрибирует его.
    Возвращает текст или None если голосовых нет или транскрибация не удалась.
    """
    url = extract_voice_url(payload)
    if not url:
        return None

    bot = bot or MaxBotService()
    try:
        audio_data = await bot.download_url(url)
    except Exception as exc:
        logger.warning("Voice download failed url=%s: %s", url[:80], exc)
        return None

    if not audio_data:
        logger.warning("Voice download returned empty data url=%s", url[:80])
        return None

    try:
        from app.core.config import get_settings
        from app.services.yandex_stt import transcribe_audio, SpeechTranscriptionError
        settings = get_settings()
        text = await transcribe_audio(audio_data, "audio/ogg", settings)
        if text:
            logger.info("Voice transcribed len=%s", len(text))
            return text.strip()
    except Exception as exc:
        logger.warning("Voice transcription failed: %s", exc)
    return None


async def load_message_vision_images(
    payload: dict[str, Any],
    *,
    bot: MaxBotService | None = None,
    message_id_value: str | None = None,
) -> list[VisionImage]:
    """Скачивает изображения из webhook-сообщения для vision-пайплайна."""
    bot = bot or MaxBotService()
    images: list[VisionImage] = []
    seen: set[str] = set()

    for att in message_attachments(payload):
        att_type = str(att.get("type") or "").lower()
        if att_type not in _IMAGE_TYPES:
            continue
        for url in _attachment_urls(att):
            if url in seen:
                continue
            seen.add(url)
            data = await bot.download_url(url)
            if not data:
                continue
            # Определяем формат по байтам — надёжнее чем URL
            from app.services.file_format import sniff_ext_from_bytes
            sniffed = sniff_ext_from_bytes(data)
            if sniffed in ("jpg", "png", "webp"):
                ext = sniffed
            elif ".png" in url.lower():
                ext = "png"
            elif ".webp" in url.lower():
                ext = "webp"
            else:
                ext = "jpg"
            # Правильный MIME: image/jpg → image/jpeg
            mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
            logger.debug(
                "VISION_DEBUG main url=%s len=%d sniffed=%s mime=%s",
                url[:60], len(data), sniffed, mime,
            )
            images.append(
                VisionImage(
                    filename=f"max-incoming.{ext}",
                    media_type=mime,
                    data_base64=base64.b64encode(data).decode("ascii"),
                )
            )

    if images:
        return images

    if message_id_value:
        messages = await bot.get_messages_by_ids([message_id_value])
        for msg in messages:
            body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
            for att in body.get("attachments") or []:
                if not isinstance(att, dict):
                    continue
                if str(att.get("type") or "").lower() not in _IMAGE_TYPES:
                    continue
                for url in _attachment_urls(att):
                    if url in seen:
                        continue
                    seen.add(url)
                    data = await bot.download_url(url)
                    if not data:
                        continue
                    from app.services.file_format import sniff_ext_from_bytes
                    sniffed = sniff_ext_from_bytes(data)
                    if sniffed in ("jpg", "png", "webp"):
                        fb_ext = sniffed
                    elif ".png" in url.lower():
                        fb_ext = "png"
                    elif ".webp" in url.lower():
                        fb_ext = "webp"
                    else:
                        fb_ext = "jpg"
                    fb_mime = "image/jpeg" if fb_ext == "jpg" else f"image/{fb_ext}"
                    logger.debug(
                        "VISION_DEBUG fallback url=%s sniffed=%s mime=%s",
                        url[:60], sniffed, fb_mime,
                    )
                    images.append(
                        VisionImage(
                            filename=f"max-incoming.{fb_ext}",
                            media_type=fb_mime,
                            data_base64=base64.b64encode(data).decode("ascii"),
                        )
                    )
    return images
