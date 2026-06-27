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

Верни ответ СТРОГО в формате (без markdown, без пояснений до/после):

{_META_DELIM}
{{"title":"...","excerpt":"1-2 предложения","meta_title":"до 60 символов","meta_description":"до 160 символов","meta_keywords":"через запятую","og_title":"...","og_description":"..."}}
{_HTML_DELIM}
<p>Вступление</p><h2>Раздел</h2><p>...</p>

Правила:
- JSON в ОДНУ строку, только двойные кавычки, без content_html внутри JSON.
- HTML только после {_HTML_DELIM}: теги p, h2, h3, ul, ol, strong, em, a.
- Объём статьи: 700–1000 слов."""


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


def _normalize_delimiters(raw: str) -> str:
    text = (raw or "").replace("\ufeff", "").strip()
    text = re.sub(r"---\s*META\s*---", _META_DELIM, text, flags=re.I)
    text = re.sub(r"---\s*HTML\s*---", _HTML_DELIM, text, flags=re.I)
    return text


def _sanitize_json_text(raw: str) -> str:
    text = raw.strip()
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u00ab", '"').replace("\u00bb", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def _repair_truncated_json(blob: str) -> str:
    text = _sanitize_json_text(blob).strip()
    if text.count('"') % 2 == 1:
        text += '"'
    text = re.sub(r',\s*"[^"]*"\s*:\s*"[^"]*$', "", text)
    text = re.sub(r',\s*"[^"]*"\s*:\s*$', "", text)
    text = text.rstrip().rstrip(",")
    if not text.endswith("}"):
        text += "}"
    return text


def _loads_json_object(raw: str) -> dict:
    cleaned = _sanitize_json_text(raw)
    attempts = [cleaned]
    blob = _extract_braced_json(cleaned)
    if blob and blob not in attempts:
        attempts.append(blob)
        attempts.append(_repair_truncated_json(blob))
    last_exc: json.JSONDecodeError | None = None
    for candidate in attempts:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if isinstance(data, dict):
            return data
        raise TypeError("expected JSON object")
    if last_exc is not None:
        raise last_exc
    raise json.JSONDecodeError("no JSON object", raw, 0)


def _strip_html_tail(raw: str) -> str:
    html = raw.strip()
    html = re.sub(r"^```(?:html)?\s*", "", html, flags=re.I)
    html = re.sub(r"\s*```\s*$", "", html)
    return html.strip()


def _extract_json_field(raw: str, key: str) -> str:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, raw, re.DOTALL)
    if not match:
        return ""
    try:
        return str(json.loads(f'"{match.group(1)}"')).strip()
    except json.JSONDecodeError:
        return match.group(1).replace('\\"', '"').strip()


def _extract_article_fallback(raw: str) -> dict:
    text = _normalize_delimiters(raw)
    html = ""
    if _HTML_DELIM in text:
        html = _strip_html_tail(text.split(_HTML_DELIM, 1)[1])
    meta_src = text.split(_META_DELIM, 1)[1].split(_HTML_DELIM, 1)[0] if _META_DELIM in text else text
    title = _extract_json_field(meta_src, "title") or _extract_json_field(text, "title")
    if not title and not html:
        raise ValueError("no parseable fields")
    return {
        "title": title,
        "excerpt": _extract_json_field(meta_src, "excerpt") or _extract_json_field(text, "excerpt"),
        "meta_title": _extract_json_field(meta_src, "meta_title") or _extract_json_field(text, "meta_title"),
        "meta_description": _extract_json_field(meta_src, "meta_description")
        or _extract_json_field(text, "meta_description"),
        "meta_keywords": _extract_json_field(meta_src, "meta_keywords") or _extract_json_field(text, "meta_keywords"),
        "og_title": _extract_json_field(meta_src, "og_title") or _extract_json_field(text, "og_title"),
        "og_description": _extract_json_field(meta_src, "og_description") or _extract_json_field(text, "og_description"),
        "content_html": html or _extract_json_field(text, "content_html"),
    }


def _parse_delimiter_format(raw: str) -> dict | None:
    text = _normalize_delimiters(raw)
    if _META_DELIM not in text or _HTML_DELIM not in text:
        return None
    meta_raw = text.split(_META_DELIM, 1)[1].split(_HTML_DELIM, 1)[0].strip()
    html_raw = _strip_html_tail(text.split(_HTML_DELIM, 1)[1])
    meta_json = _extract_braced_json(meta_raw) or meta_raw
    try:
        data = _loads_json_object(meta_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        data = _extract_article_fallback(text)
    if not isinstance(data, dict):
        return None
    if html_raw:
        data["content_html"] = html_raw
    return data


def _parse_json_blob(text: str) -> dict:
    raw = _normalize_delimiters(text)
    delimited = _parse_delimiter_format(raw)
    if delimited is not None:
        return delimited

    if _HTML_DELIM in raw:
        html_raw = _strip_html_tail(raw.split(_HTML_DELIM, 1)[1])
        head = raw.split(_HTML_DELIM, 1)[0]
        try:
            data = _loads_json_object(head)
            data["content_html"] = html_raw
            return data
        except (json.JSONDecodeError, TypeError, ValueError):
            data = _extract_article_fallback(raw)
            if data.get("title") or data.get("content_html"):
                return data

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence and _META_DELIM not in raw:
        try:
            return _loads_json_object(fence.group(1).strip())
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    try:
        return _loads_json_object(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        data = _extract_article_fallback(raw)
        if data.get("title") or data.get("content_html"):
            return data
        raise


def _string_field(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    return str(value or default).strip()


def _parse_article_response(text: str, *, topic: str) -> dict:
    try:
        return _parse_json_blob(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Blog article JSON parse failed: %s; head=%r", exc, (text or "")[:400])
        raise ValueError(
            "Модель вернула некорректный формат. Попробуйте ещё раз или упростите требования."
        ) from exc


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
    user_prompt += "Объём: 700–1000 слов. HTML: p, h2, h3, ul, ol, strong, em, a."
    messages = [
        {"role": "system", "text": _BLOG_SYSTEM},
        {"role": "user", "text": user_prompt[:4000]},
    ]
    text = await llm.complete_text(
        messages,
        model="pro",
        max_tokens=8192,
        temperature=0.55,
    )
    try:
        data = _parse_article_response(text, topic=topic)
    except ValueError:
        repair_user = (
            "Исправь формат ответа. Верни ТОЛЬКО блоки META и HTML как в инструкции.\n"
            f"Тема: {topic.strip()}\n"
            f"Исходный ответ модели:\n{(text or '')[:7000]}"
        )
        repaired = await llm.complete_text(
            [
                {"role": "system", "text": _BLOG_SYSTEM},
                {"role": "user", "text": repair_user[:8000]},
            ],
            model="pro",
            max_tokens=8192,
            temperature=0.2,
        )
        data = _parse_article_response(repaired, topic=topic)
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
    # Check if the selected provider is configured
    if provider_id == "gigachat" and not settings.gigachat_configured:
        raise ImageGenerationError(
            "provider_unavailable",
            "Генерация изображений недоступна: настройте GigaChat (GIGACHAT_CREDENTIALS).",
        )
    if provider_id == "nanab2" and not settings.google_configured:
        raise ImageGenerationError(
            "provider_unavailable",
            "Генерация изображений недоступна: настройте Nano Banana (GOOGLE_API_KEY).",
        )
    if provider_id not in ("gigachat", "nanab2"):
        raise ImageGenerationError(
            "provider_unavailable",
            f"Провайдер генерации изображений '{provider_id}' не поддерживается.",
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
