"""AI helpers for admin blog authoring (Pro-level providers)."""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.blog import BlogMedia
from app.services.blog_image import process_blog_image
from app.services.blog_posts import blog_media_url
from app.services.blog_sanitize import sanitize_blog_html
from app.services.blog_slug import ensure_unique_post_slug, slugify_title
from app.services.blog_storage import save_blog_image
from app.services.gigachat_image_gen import ImageGenerationError
from app.services.image_bytes import is_valid_image_bytes
from app.services.image_gen_service import generate_image, resolve_image_gen_provider_id
from app.services.prompts.store import PromptStore
from app.services.providers.factory import create_llm_provider, resolve_llm_provider_id

logger = logging.getLogger(__name__)

_META_DELIM = "---META---"
_HTML_DELIM = "---HTML---"

_BLOG_SYSTEM = f"""Ты редактор блога Glosix — ИИ-поиска и ассистента.
Пиши на русском, информативно и без воды. Структура: вступление, H2-разделы, вывод.

Верни ответ СТРОГО в формате (без markdown-обёртки):

{_META_DELIM}
{{"title":"...","excerpt":"1-2 предложения","meta_title":"до 60 символов","meta_description":"до 160 символов","meta_keywords":"через запятую","og_title":"...","og_description":"..."}}

{_HTML_DELIM}
<p>Вступление</p><h2>Раздел</h2><p>...</p>

Правила:
- В JSON НЕ включай content_html и не используй многострочные строки.
- HTML пиши после {_HTML_DELIM} отдельно: теги p, h2, h3, ul, ol, strong, em, a.
- Объём статьи: 800–1200 слов."""


async def _admin_pro_llm(db: AsyncSession, redis_client):
    settings = get_settings()
    prompt_store = PromptStore(db, redis_client)
    llm_id = await resolve_llm_provider_id(db, redis_client)
    return create_llm_provider(llm_id, settings, prompt_store)


def _extract_braced_json(raw: str) -> str | None:
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : idx + 1]
    return None


def _parse_json_blob(text: str) -> dict:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()

    if _META_DELIM in raw and _HTML_DELIM in raw:
        meta_raw = raw.split(_META_DELIM, 1)[1].split(_HTML_DELIM, 1)[0].strip()
        html_raw = raw.split(_HTML_DELIM, 1)[1].strip()
        meta_json = _extract_braced_json(meta_raw) or meta_raw
        data = json.loads(meta_json)
        if isinstance(data, dict):
            data["content_html"] = html_raw
            return data

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        blob = _extract_braced_json(raw)
        if blob:
            return json.loads(blob)
        raise


def _string_field(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    return str(value or default).strip()


async def generate_blog_article(
    db: AsyncSession,
    redis_client,
    *,
    topic: str,
    requirements: str,
    fill_seo: bool,
    generate_slug: bool,
) -> dict:
    llm = await _admin_pro_llm(db, redis_client)
    user_prompt = f"Тема: {topic.strip()}\n"
    if requirements.strip():
        user_prompt += f"Требования: {requirements.strip()}\n"
    user_prompt += "Объём: 800–1200 слов. HTML: p, h2, h3, ul, ol, strong, em, a."
    text = await llm.complete_text(
        [
            {"role": "system", "text": _BLOG_SYSTEM},
            {"role": "user", "text": user_prompt[:4000]},
        ],
        model="pro",
        max_tokens=4000,
        temperature=0.65,
    )
    try:
        data = _parse_json_blob(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Blog article JSON parse failed: %s; head=%r", exc, (text or "")[:400])
        raise ValueError(
            "Модель вернула некорректный формат. Попробуйте ещё раз или упростите требования."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("Модель вернула не объект JSON")

    title = _string_field(data, "title", topic)
    excerpt = _string_field(data, "excerpt")
    content_html = sanitize_blog_html(_string_field(data, "content_html", "<p></p>") or "<p></p>")
    slug = slugify_title(title)
    if generate_slug:
        slug = await ensure_unique_post_slug(db, slug, locale="ru")
    meta_title = _string_field(data, "meta_title", title) if fill_seo else ""
    meta_description = _string_field(data, "meta_description", excerpt) if fill_seo else ""
    meta_keywords = _string_field(data, "meta_keywords") if fill_seo else ""
    og_title = _string_field(data, "og_title", meta_title or title) if fill_seo else ""
    og_description = _string_field(data, "og_description", meta_description) if fill_seo else ""
    return {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "content_html": content_html,
        "meta_title": meta_title[:255],
        "meta_description": meta_description[:500],
        "meta_keywords": meta_keywords[:500],
        "og_title": og_title[:255],
        "og_description": og_description[:500],
    }


async def _generate_blog_image_media(
    db: AsyncSession,
    redis_client,
    *,
    prompt: str,
    alt_text: str,
    purpose: str,
    admin_id: UUID | None,
) -> BlogMedia:
    settings = get_settings()
    provider_id = await resolve_image_gen_provider_id(db, redis_client)
    if provider_id != "gigachat" or not settings.gigachat_configured:
        raise ImageGenerationError(
            "provider_unavailable",
            "Генерация изображений недоступна: настройте GigaChat (GIGACHAT_CREDENTIALS) и image_gen_provider=gigachat.",
        )
    try:
        image_bytes, _ = await generate_image(prompt, provider_id)
    except ImageGenerationError:
        raise
    except Exception as exc:
        logger.exception("Blog image generation failed")
        raise ImageGenerationError("generation_failed", str(exc) or "Ошибка генерации изображения") from exc

    if not image_bytes or not is_valid_image_bytes(image_bytes):
        raise ImageGenerationError("generation_failed", "Провайдер вернул пустое или повреждённое изображение")

    try:
        processed = process_blog_image(image_bytes, purpose=purpose)
    except Exception as exc:
        logger.exception("Blog image post-process failed")
        raise ImageGenerationError("generation_failed", "Не удалось обработать сгенерированное изображение") from exc

    media_id = uuid4()
    storage_key = save_blog_image(media_id, processed.data)
    media = BlogMedia(
        id=media_id,
        filename=f"{purpose}-{media_id.hex[:8]}.webp",
        storage_key=storage_key,
        mime_type=processed.mime_type,
        size_bytes=len(processed.data),
        width=processed.width,
        height=processed.height,
        alt_text=alt_text.strip() or prompt[:200],
        purpose=purpose,
        created_by_admin_id=admin_id,
    )
    db.add(media)
    await db.flush()
    return media


async def generate_blog_cover(
    db: AsyncSession,
    redis_client,
    *,
    prompt: str,
    alt_text: str,
    admin_id: UUID | None,
) -> BlogMedia:
    return await _generate_blog_image_media(
        db,
        redis_client,
        prompt=prompt,
        alt_text=alt_text,
        purpose="cover",
        admin_id=admin_id,
    )


async def generate_blog_inline_image(
    db: AsyncSession,
    redis_client,
    *,
    prompt: str,
    alt_text: str,
    admin_id: UUID | None,
) -> BlogMedia:
    return await _generate_blog_image_media(
        db,
        redis_client,
        prompt=prompt,
        alt_text=alt_text,
        purpose="inline",
        admin_id=admin_id,
    )


def media_upload_out(media: BlogMedia) -> dict:
    return {
        "id": media.id,
        "url": blog_media_url(media.id),
        "width": media.width,
        "height": media.height,
        "alt_text": media.alt_text,
        "size_bytes": media.size_bytes,
    }
