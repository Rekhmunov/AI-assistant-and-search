"""MAX Bot: загрузка медиа и вложения image/video к сообщениям."""

from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile, status

from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

WELCOME_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
WELCOME_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
MAX_MEDIA_BYTES = 50 * 1024 * 1024


def media_type_from_filename(filename: str) -> str | None:
    name = (filename or "media").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in WELCOME_IMAGE_EXT:
        return "image"
    if ext in WELCOME_VIDEO_EXT:
        return "video"
    return None


def max_bot_media_attachments(media_type: str | None, media_token: str | None) -> list[dict] | None:
    """Вложение фото/видео/файла над текстом (как в MAX Bot API)."""
    mt = (media_type or "none").strip().lower()
    token = (media_token or "").strip()
    if mt in {"image", "video", "file"} and token:
        return [{"type": mt, "payload": {"token": token}}]
    return None


async def read_and_upload_max_media(file: UploadFile) -> tuple[str, str, str]:
    """Возвращает (media_type, media_token, media_filename)."""
    filename = file.filename or "media"
    media_type = media_type_from_filename(filename)
    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются изображения (jpg, png, webp, gif) и видео (mp4, mov, webm)",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл больше 50 МБ")

    bot = MaxBotService()
    token = await bot.upload_media(data, filename, media_type)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось загрузить файл в MAX. Проверьте BOT_TOKEN.",
        )
    return media_type, token, filename
