"""Загрузка файлов и изображений в MAX для агента."""

from __future__ import annotations

import asyncio
import logging
import mimetypes

from app.services.bot import (
    FILE_UPLOAD_TO_SEND_DELAY_SEC,
    MaxBotService,
    UPLOAD_TO_SEND_DELAY_SEC,
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tiff"}


def attachment_type_for_filename(filename: str) -> str:
    name = (filename or "file").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "file"


def max_file_attachment(token: str) -> dict:
    return {"type": "file", "payload": {"token": token}}


def max_image_attachment(token: str) -> dict:
    return {"type": "image", "payload": {"token": token}}


async def upload_bytes_to_max(
    data: bytes,
    filename: str,
    *,
    bot: MaxBotService | None = None,
) -> tuple[str | None, list[dict]]:
    """Загружает байты в MAX и возвращает (token, attachments)."""
    if not data:
        return None, []
    bot = bot or MaxBotService()
    media_type = attachment_type_for_filename(filename)
    token = await bot.upload_media(data, filename, media_type)
    if not token:
        return None, []
    delay = UPLOAD_TO_SEND_DELAY_SEC if media_type == "image" else FILE_UPLOAD_TO_SEND_DELAY_SEC
    await asyncio.sleep(delay)
    if media_type == "image":
        return token, [max_image_attachment(token)]
    return token, [max_file_attachment(token)]
