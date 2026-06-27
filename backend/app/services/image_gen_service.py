"""Фасад генерации изображений по настройке image_gen_provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.image_gen import GENERATED_IMAGE_TTL_HOURS, MAX_IMAGE_GEN_PROMPT_LEN
from app.core.config import Settings, get_settings
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.app_settings import get_setting
from app.services.entity_image import EntityImage, entity_images_to_json
from app.services.gigachat_image_gen import (
    ImageGenerationError,
    generate_gigachat_image,
    stream_gigachat_image_generation,
)
from app.services.image_gen_routing import image_generation_prompt
from app.services.providers.registry import DEFAULT_IMAGE_GEN_PROVIDER, VALID_IMAGE_GEN_IDS
from app.services.upload_storage import save_upload_bytes


def public_file_content_url(file_id: UUID, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    base = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    return f"{base}/api/files/{file_id}/content"


async def resolve_image_gen_provider_id(db: AsyncSession, redis_client: redis.Redis) -> str:
    raw = await get_setting("image_gen_provider", db, redis_client)
    pid = str(raw or DEFAULT_IMAGE_GEN_PROVIDER).strip()
    return pid if pid in VALID_IMAGE_GEN_IDS else DEFAULT_IMAGE_GEN_PROVIDER


async def persist_generated_image(
    db: AsyncSession,
    user: User,
    image_bytes: bytes,
    *,
    title: str,
    ttl_hours: int | None = None,
) -> tuple[UUID, list[dict]]:
    from app.services.image_bytes import detect_image_mime

    mime = detect_image_mime(image_bytes) or "image/jpeg"
    ext = "png" if mime == "image/png" else "jpg"
    file_id = uuid4()
    now = datetime.now(timezone.utc)
    hours = ttl_hours if ttl_hours is not None else GENERATED_IMAGE_TTL_HOURS
    hours = max(1, min(int(hours), 24 * 30))
    storage_key = save_upload_bytes(user.id, file_id, image_bytes, ext)
    row = UploadedFile(
        id=file_id,
        user_id=user.id,
        filename=f"generated-{file_id.hex[:8]}.{ext}",
        mime_type=mime,
        size_bytes=len(image_bytes),
        media_kind="generated",
        storage_key=storage_key,
        extracted_text="",
        expires_at=now + timedelta(hours=hours),
    )
    db.add(row)
    await db.flush()
    settings = get_settings()
    url = public_file_content_url(file_id, settings)
    images = entity_images_to_json(
        [
            EntityImage(
                url=url,
                title=title[:200] or "Сгенерированное изображение",
                page_url=url,
            )
        ]
    )
    return file_id, images


async def stream_image_generation(
    prompt: str,
    provider_id: str,
) -> AsyncIterator[tuple[str, str]]:
    text = image_generation_prompt(prompt)[:MAX_IMAGE_GEN_PROMPT_LEN]
    if provider_id == "gigachat":
        async for item in stream_gigachat_image_generation(text):
            yield item
    elif provider_id == "nanab2":
        # Nano Banana: no streaming — generate fully then emit same events as GigaChat
        try:
            from app.services.nano_banana import generate_nano_banana_image
            settings = get_settings()
            result = await generate_nano_banana_image(text, api_key=settings.google_api_key)
            yield ("image_bytes", result.image_bytes)                   # consumer expects bytes
            yield ("done", f"\n{result.assistant_text}")                 # consumer reads line[1] as text
        except ImageGenerationError as exc:
            yield ("error", str(exc))
    else:
        yield ("error", "Провайдер генерации изображений не поддерживается")


async def generate_image(
    prompt: str,
    provider_id: str,
) -> tuple[bytes, str]:
    text = image_generation_prompt(prompt)[:MAX_IMAGE_GEN_PROMPT_LEN]
    if provider_id == "gigachat":
        result = await generate_gigachat_image(text)
        return result.image_bytes, result.assistant_text
    elif provider_id == "nanab2":
        from app.services.nano_banana import generate_nano_banana_image
        settings = get_settings()
        result = await generate_nano_banana_image(text, api_key=settings.google_api_key)
        return result.image_bytes, result.assistant_text
    raise ImageGenerationError("provider_unavailable", "Провайдер не настроен")
