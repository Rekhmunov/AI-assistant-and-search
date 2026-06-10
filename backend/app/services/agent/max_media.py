"""Извлечение и загрузка изображений из сообщений MAX."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.services.attachment_bundle import VisionImage
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_IMAGE_TYPES = frozenset({"image", "photo"})


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
            ext = "jpg"
            if ".png" in url.lower():
                ext = "png"
            elif ".webp" in url.lower():
                ext = "webp"
            images.append(
                VisionImage(
                    filename=f"max-incoming.{ext}",
                    media_type=f"image/{ext}",
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
                    images.append(
                        VisionImage(
                            filename="max-incoming.jpg",
                            media_type="image/jpeg",
                            data_base64=base64.b64encode(data).decode("ascii"),
                        )
                    )
    return images
