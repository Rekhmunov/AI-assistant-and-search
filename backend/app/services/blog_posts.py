"""Blog post/category business logic."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.blog import BlogCategory, BlogMedia, BlogPost, BlogSlugRedirect
from app.services.blog_sanitize import estimate_reading_time_min, sanitize_blog_html
from app.services.blog_slug import ensure_unique_post_slug, is_valid_slug, slugify_title


def blog_media_url(media_id: UUID) -> str:
    return f"/api/blog/media/{media_id}"


def media_out(media: BlogMedia | None) -> dict | None:
    if not media:
        return None
    return {
        "id": media.id,
        "url": blog_media_url(media.id),
        "width": media.width,
        "height": media.height,
        "alt_text": media.alt_text or "",
        "size_bytes": media.size_bytes,
    }


async def list_categories(db: AsyncSession) -> list[BlogCategory]:
    result = await db.execute(select(BlogCategory).order_by(BlogCategory.sort_order, BlogCategory.name))
    return list(result.scalars().all())


async def get_category_by_slug(db: AsyncSession, slug: str) -> BlogCategory | None:
    result = await db.execute(select(BlogCategory).where(BlogCategory.slug == slug))
    return result.scalar_one_or_none()


DEFAULT_LOCALE = "ru"


def blog_canonical_path(slug: str, locale: str = DEFAULT_LOCALE) -> str:
    if locale == "ru":
        return f"/blog/{slug}"
    return f"/{locale}/blog/{slug}"


async def get_post_by_slug(db: AsyncSession, slug: str, *, locale: str = DEFAULT_LOCALE) -> BlogPost | None:
    result = await db.execute(
        select(BlogPost)
        .where(BlogPost.slug == slug, BlogPost.locale == locale)
        .options(
            selectinload(BlogPost.category),
            selectinload(BlogPost.cover_image),
            selectinload(BlogPost.og_image),
        )
    )
    return result.scalar_one_or_none()


async def resolve_slug_redirect(db: AsyncSession, slug: str) -> BlogPost | None:
    row = await db.execute(select(BlogSlugRedirect).where(BlogSlugRedirect.old_slug == slug))
    redirect = row.scalar_one_or_none()
    if not redirect:
        return None
    result = await db.execute(
        select(BlogPost)
        .where(BlogPost.id == redirect.post_id)
        .options(
            selectinload(BlogPost.category),
            selectinload(BlogPost.cover_image),
            selectinload(BlogPost.og_image),
        )
    )
    return result.scalar_one_or_none()


def post_to_public(post: BlogPost) -> dict:
    og = post.og_image or post.cover_image
    meta_title = post.meta_title.strip() or post.title
    meta_desc = post.meta_description.strip() or post.excerpt.strip()
    og_title = post.og_title.strip() or meta_title
    og_desc = post.og_description.strip() or meta_desc
    return {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "excerpt": post.excerpt,
        "content_html": post.content_html,
        "published_at": post.published_at,
        "updated_at": post.updated_at,
        "reading_time_min": post.reading_time_min,
        "category": post.category,
        "cover_image": media_out(post.cover_image),
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "meta_keywords": post.meta_keywords,
        "og_title": og_title,
        "og_description": og_desc,
        "og_image": media_out(og),
        "author_name": post.author_name or "",
        "comments_enabled": bool(post.comments_enabled),
        "locale": post.locale or DEFAULT_LOCALE,
        "canonical_path": blog_canonical_path(post.slug, post.locale or DEFAULT_LOCALE),
        "robots_index": post.robots_index and post.status == "published",
        "view_count": post.view_count or 0,
    }


def post_to_admin(post: BlogPost, *, author_email: str | None = None) -> dict:
    return {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "excerpt": post.excerpt,
        "status": post.status,
        "published_at": post.published_at,
        "reading_time_min": post.reading_time_min,
        "category": post.category,
        "cover_image": media_out(post.cover_image),
        "content_html": post.content_html,
        "category_id": post.category_id,
        "cover_image_id": post.cover_image_id,
        "og_image_id": post.og_image_id,
        "meta_title": post.meta_title,
        "meta_description": post.meta_description,
        "meta_keywords": post.meta_keywords,
        "og_title": post.og_title,
        "og_description": post.og_description,
        "robots_index": post.robots_index,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "author_email": author_email,
        "author_name": post.author_name or "",
        "comments_enabled": bool(post.comments_enabled),
        "locale": post.locale or DEFAULT_LOCALE,
        "view_count": post.view_count or 0,
    }


async def list_posts_admin(
    db: AsyncSession,
    *,
    status: str | None = None,
    category_id: UUID | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[BlogPost], int]:
    q = select(BlogPost).options(
        selectinload(BlogPost.category),
        selectinload(BlogPost.cover_image),
    )
    count_q = select(func.count()).select_from(BlogPost)
    if status:
        q = q.where(BlogPost.status == status)
        count_q = count_q.where(BlogPost.status == status)
    if category_id:
        q = q.where(BlogPost.category_id == category_id)
        count_q = count_q.where(BlogPost.category_id == category_id)
    if search:
        term = f"%{search.strip()}%"
        q = q.where(BlogPost.title.ilike(term))
        count_q = count_q.where(BlogPost.title.ilike(term))
    total = int(await db.scalar(count_q) or 0)
    q = q.order_by(BlogPost.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def list_posts_public(
    db: AsyncSession,
    *,
    category_slug: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[BlogPost], int]:
    q = (
        select(BlogPost)
        .where(
            BlogPost.status == "published",
            BlogPost.published_at.is_not(None),
            BlogPost.locale == DEFAULT_LOCALE,
        )
        .options(selectinload(BlogPost.category), selectinload(BlogPost.cover_image))
    )
    count_q = select(func.count()).select_from(BlogPost).where(
        BlogPost.status == "published",
        BlogPost.published_at.is_not(None),
        BlogPost.locale == DEFAULT_LOCALE,
    )
    if category_slug:
        cat = await get_category_by_slug(db, category_slug)
        if not cat:
            return [], 0
        q = q.where(BlogPost.category_id == cat.id)
        count_q = count_q.where(BlogPost.category_id == cat.id)
    total = int(await db.scalar(count_q) or 0)
    q = q.order_by(BlogPost.published_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


def _apply_publish_fields(post: BlogPost, status: str, published_at: datetime | None) -> None:
    now = datetime.now(timezone.utc)
    if status == "published":
        if not post.published_at:
            post.published_at = published_at or now
        post.robots_index = True
    elif status == "draft":
        post.robots_index = False


async def create_post(db: AsyncSession, data: dict, *, admin_id: UUID | None) -> BlogPost:
    title = data["title"].strip()
    slug_input = (data.get("slug") or "").strip()
    base_slug = slugify_title(slug_input or title)
    if slug_input and not is_valid_slug(slug_input):
        raise ValueError("invalid_slug")
    if slug_input and is_valid_slug(slug_input):
        base_slug = slug_input
    locale = (data.get("locale") or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE
    slug = await ensure_unique_post_slug(db, base_slug, locale=locale)
    content = sanitize_blog_html(data.get("content_html") or "<p></p>")
    status = data.get("status") or "draft"
    post = BlogPost(
        slug=slug,
        title=title,
        excerpt=(data.get("excerpt") or "").strip(),
        content_html=content,
        status=status,
        category_id=data.get("category_id"),
        cover_image_id=data.get("cover_image_id"),
        og_image_id=data.get("og_image_id"),
        author_admin_id=admin_id,
        author_name=(data.get("author_name") or "").strip(),
        comments_enabled=bool(data.get("comments_enabled", False)),
        locale=locale,
        meta_title=(data.get("meta_title") or "").strip(),
        meta_description=(data.get("meta_description") or "").strip(),
        meta_keywords=(data.get("meta_keywords") or "").strip(),
        og_title=(data.get("og_title") or "").strip(),
        og_description=(data.get("og_description") or "").strip(),
        robots_index=bool(data.get("robots_index", True)),
        reading_time_min=estimate_reading_time_min(content),
    )
    _apply_publish_fields(post, status, data.get("published_at"))
    db.add(post)
    await db.flush()
    return post


async def update_post(db: AsyncSession, post: BlogPost, data: dict) -> BlogPost:
    if "title" in data and data["title"] is not None:
        post.title = data["title"].strip()
    if "slug" in data and data["slug"] is not None:
        new_slug = data["slug"].strip()
        if new_slug:
            if not is_valid_slug(new_slug):
                raise ValueError("invalid_slug")
            if new_slug != post.slug:
                unique = await ensure_unique_post_slug(
                    db, new_slug, locale=post.locale or DEFAULT_LOCALE, exclude_id=post.id
                )
                old = post.slug
                post.slug = unique
                db.add(BlogSlugRedirect(old_slug=old, post_id=post.id))
    if "excerpt" in data and data["excerpt"] is not None:
        post.excerpt = data["excerpt"].strip()
    if "content_html" in data and data["content_html"] is not None:
        post.content_html = sanitize_blog_html(data["content_html"])
        post.reading_time_min = estimate_reading_time_min(post.content_html)
    if "status" in data and data["status"] is not None:
        post.status = data["status"]
        _apply_publish_fields(post, post.status, data.get("published_at"))
    elif "published_at" in data:
        _apply_publish_fields(post, post.status, data.get("published_at"))
    # FK fields accept None to clear the association
    for field in ("category_id", "cover_image_id", "og_image_id"):
        if field in data:
            setattr(post, field, data[field])
    # Scalar fields: skip if None to preserve existing value
    for field in (
        "meta_title",
        "meta_description",
        "meta_keywords",
        "og_title",
        "og_description",
        "robots_index",
        "author_name",
        "comments_enabled",
        "locale",
    ):
        if field in data and data[field] is not None:
            setattr(post, field, data[field])
    # view_count: admin can set an arbitrary initial value (≥0)
    if "view_count" in data and data["view_count"] is not None:
        post.view_count = max(0, int(data["view_count"]))
    await db.flush()
    return post
