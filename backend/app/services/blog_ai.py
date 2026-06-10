"""AI helpers for admin blog authoring (Pro-level providers)."""

from __future__ import annotations

import json
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
from app.services.prompts.store import PromptStore
from app.services.image_gen_service import generate_image, resolve_image_gen_provider_id
from app.services.providers.factory import create_llm_provider, resolve_llm_provider_id

_BLOG_SYSTEM = """Ты редактор блога Glosix — ИИ-поиска и ассистента.
Пиши на русском, информативно и без воды. Структура: вступление, H2-разделы, вывод.
Верни ТОЛЬКО JSON без markdown-обёртки:
{
  "title": "...",
  "excerpt": "1-2 предложения",
  "content_html": "<p>...</p><h2>...</h2>...",
  "meta_title": "до 60 символов",
  "meta_description": "до 160 символов",
  "meta_keywords": "через запятую",
  "og_title": "...",
  "og_description": "..."
}"""


async def _admin_pro_llm(db: AsyncSession, redis_client):
    settings = get_settings()
    prompt_store = PromptStore(db, redis_client)
    llm_id = await resolve_llm_provider_id(db, redis_client)
    return create_llm_provider(llm_id, settings, prompt_store)


def _parse_json_blob(text: str) -> dict:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    return json.loads(raw)


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
    data = _parse_json_blob(text)
    title = str(data.get("title") or topic).strip()
    excerpt = str(data.get("excerpt") or "").strip()
    content_html = sanitize_blog_html(str(data.get("content_html") or "<p></p>"))
    slug = slugify_title(title)
    if generate_slug:
        slug = await ensure_unique_post_slug(db, slug, locale="ru")
    meta_title = str(data.get("meta_title") or title).strip() if fill_seo else ""
    meta_description = str(data.get("meta_description") or excerpt).strip() if fill_seo else ""
    meta_keywords = str(data.get("meta_keywords") or "").strip() if fill_seo else ""
    og_title = str(data.get("og_title") or meta_title or title).strip() if fill_seo else ""
    og_description = str(data.get("og_description") or meta_description).strip() if fill_seo else ""
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


async def generate_blog_cover(
    db: AsyncSession,
    redis_client,
    *,
    prompt: str,
    alt_text: str,
    admin_id: UUID | None,
) -> BlogMedia:
    provider_id = await resolve_image_gen_provider_id(db, redis_client)
    image_bytes, _ = await generate_image(prompt, provider_id)
    processed = process_blog_image(image_bytes, purpose="cover")
    media_id = uuid4()
    storage_key = save_blog_image(media_id, processed.data)
    media = BlogMedia(
        id=media_id,
        filename=f"cover-{media_id.hex[:8]}.webp",
        storage_key=storage_key,
        mime_type=processed.mime_type,
        size_bytes=len(processed.data),
        width=processed.width,
        height=processed.height,
        alt_text=alt_text.strip() or prompt[:200],
        purpose="cover",
        created_by_admin_id=admin_id,
    )
    db.add(media)
    await db.flush()
    return media


def media_upload_out(media: BlogMedia) -> dict:
    return {
        "id": media.id,
        "url": blog_media_url(media.id),
        "width": media.width,
        "height": media.height,
        "alt_text": media.alt_text,
        "size_bytes": media.size_bytes,
    }
