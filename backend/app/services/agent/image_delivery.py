"""Генерация изображения и подготовка вложения для MAX."""

from __future__ import annotations

import asyncio
import logging

from app.services.bot import MaxBotService, UPLOAD_TO_SEND_DELAY_SEC
from app.services.gigachat_image_gen import ImageGenerationError, generate_gigachat_image

logger = logging.getLogger(__name__)


async def build_image_attachments(
    prompt: str,
    *,
    bot: MaxBotService | None = None,
) -> tuple[str, list[dict]]:
    """Возвращает (текст подписи, attachments для send_message)."""
    prompt = (prompt or "").strip()
    if not prompt:
        return "Изображение не сгенерировано: пустой промпт.", []

    try:
        result = await generate_gigachat_image(prompt[:2000])
    except ImageGenerationError as exc:
        logger.warning("Agent image gen failed: %s", exc)
        return f"Не удалось сгенерировать изображение: {exc}", []
    except Exception as exc:
        logger.warning("Agent image gen error: %s", exc)
        return "Не удалось сгенерировать изображение. Попробуйте позже.", []

    bot = bot or MaxBotService()
    token = await bot.upload_media(result.image_bytes, "agent-image.jpg", "image")
    if token:
        # dev.max.ru/docs-api/methods/POST/uploads — пауза после upload, иначе attachment.not.ready
        await asyncio.sleep(UPLOAD_TO_SEND_DELAY_SEC)
    if not token:
        caption = (result.assistant_text or "Изображение").strip()[:500]
        return caption or "Изображение сгенерировано, но не удалось загрузить в MAX.", []

    caption = (result.assistant_text or prompt).strip()[:500]
    attachments = [{"type": "image", "payload": {"token": token}}]
    return caption, attachments
