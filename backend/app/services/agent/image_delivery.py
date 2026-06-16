"""Генерация изображения и подготовка вложения для MAX."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bot import MaxBotService, UPLOAD_TO_SEND_DELAY_SEC
from app.services.gigachat_image_gen import ImageGenerationError, generate_gigachat_image

logger = logging.getLogger(__name__)


async def build_image_attachments(
    prompt: str,
    *,
    bot: MaxBotService | None = None,
    db: AsyncSession | None = None,
    user=None,
    redis_client=None,
) -> tuple[str, list[dict], str | None]:
    """
    Возвращает (caption, attachments, share_url).

    share_url — подписанная ссылка для скачивания (без Bearer), доступна если
    переданы db + user. Используется для кнопки «Скачать» в inline_keyboard MAX.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return "Изображение не сгенерировано: пустой промпт.", [], None

    try:
        result = await generate_gigachat_image(prompt[:2000])
    except ImageGenerationError as exc:
        logger.warning("Agent image gen failed: %s", exc)
        return f"Не удалось сгенерировать изображение: {exc}", [], None
    except Exception as exc:
        logger.warning("Agent image gen error: %s", exc)
        return "Не удалось сгенерировать изображение. Попробуйте позже.", [], None

    bot = bot or MaxBotService()
    token = await bot.upload_media(result.image_bytes, "agent-image.jpg", "image")
    if token:
        await asyncio.sleep(UPLOAD_TO_SEND_DELAY_SEC)

    attachments: list[dict] = []
    if token:
        attachments = [{"type": "image", "payload": {"token": token}}]

    # Сохраняем в хранилище и генерируем share-ссылку для кнопки «Скачать»
    share_url: str | None = None
    if db is not None and user is not None:
        share_url = await _persist_and_share(
            db, user, result.image_bytes, prompt, redis_client=redis_client
        )

    caption = (result.assistant_text or prompt).strip()[:500]
    if not attachments:
        caption = caption or "Изображение сгенерировано, но не удалось загрузить в MAX."

    return caption, attachments, share_url


async def _persist_and_share(
    db: AsyncSession,
    user,
    image_bytes: bytes,
    title: str,
    *,
    redis_client=None,
) -> str | None:
    """Сохраняет байты в storage, возвращает share-URL или None при ошибке."""
    try:
        from app.services.image_gen_service import persist_generated_image
        from app.services.upload_lifecycle import resolve_generated_image_ttl_hours
        from app.services.file_share_token import (
            create_file_share_token,
            share_token_ttl_seconds_for_expires_at,
        )
        from app.core.config import get_settings

        ttl_hours = await resolve_generated_image_ttl_hours(db, redis_client)
        file_id, _ = await persist_generated_image(
            db, user, image_bytes, title=title[:120], ttl_hours=ttl_hours
        )
        await db.flush()

        # Вычисляем TTL share-токена, совпадающий с TTL файла
        from sqlalchemy import select
        from app.models.uploaded_file import UploadedFile

        row_res = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
        row = row_res.scalar_one_or_none()
        ttl_sec = share_token_ttl_seconds_for_expires_at(row.expires_at if row else None)

        settings = get_settings()
        share_tok, _ = create_file_share_token(file_id, ttl_seconds=ttl_sec, settings=settings)
        base = (settings.public_web_url or "https://glosix.ru").rstrip("/")
        return f"{base}/api/files/{file_id}/shared?token={share_tok}"
    except Exception as exc:
        logger.warning("image_delivery: failed to persist/share image: %s", exc)
        return None
