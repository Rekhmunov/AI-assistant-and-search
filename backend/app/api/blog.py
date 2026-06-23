from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_rate_limiter, get_redis
from app.core.auth_limits import client_ip
from app.core.limiter import RateLimiter
from app.models.blog import BlogMedia, BlogPost
from app.schemas.blog import BlogCategoryOut, BlogCommentCreate, BlogCommentOut, BlogPostListItem
from app.services.blog_comments import add_comment, list_approved_comments
from app.services.blog_posts import (
    DEFAULT_LOCALE,
    blog_media_url,
    get_post_by_slug,
    get_category_by_slug,
    list_categories,
    list_posts_public,
    get_related_posts,
    get_neighbor_posts,
    media_out,
    post_to_public,
    resolve_slug_redirect,
)
from app.services.blog_storage import load_blog_image
from app.services.upload_storage import mime_for_ext

router = APIRouter(prefix="/blog", tags=["blog"])


@router.get("/categories", response_model=list[BlogCategoryOut])
async def public_categories(db: Annotated[AsyncSession, Depends(get_db)]):
    return await list_categories(db)


@router.get("/posts", response_model=list[BlogPostListItem])
async def public_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
):
    posts, _ = await list_posts_public(db, category_slug=category, search=search, offset=offset, limit=limit)
    return [
        {
            "id": p.id,
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt,
            "published_at": p.published_at,
            "reading_time_min": p.reading_time_min,
            "view_count": p.view_count or 0,
            "tags": p.tags or [],
            "category": p.category,
            "cover_image": media_out(p.cover_image),
        }
        for p in posts
    ]


@router.post("/posts/{slug}/view", status_code=status.HTTP_204_NO_CONTENT)
async def public_post_view(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
):
    """
    Инкрементирует счётчик просмотров статьи.
    Защита от накрутки: один IP — один просмотр в 24 часа.
    Redis-ключ: blog:views:{post_id} — буфер, сбрасывается в БД каждые 20 просмотров.
    """
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        return  # тихо игнорируем

    ip = client_ip(request)
    dedup_key = f"blog:view_ip:{post.id}:{ip}"
    already_viewed = await redis.set(dedup_key, "1", nx=True, ex=86400)  # 24 часа
    if not already_viewed:
        return  # уже считали этот IP сегодня

    counter_key = f"blog:views:{post.id}"
    count = await redis.incr(counter_key)

    # Каждые 20 просмотров — сбрасываем в БД атомарно
    FLUSH_EVERY = 20
    if count % FLUSH_EVERY == 0:
        await redis.set(counter_key, 0)
        await db.execute(
            update(BlogPost)
            .where(BlogPost.id == post.id)
            .values(view_count=BlogPost.view_count + FLUSH_EVERY)
        )
        await db.commit()


@router.get("/posts/{slug}/comments", response_model=list[BlogCommentOut])
async def public_post_comments(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published" or not post.comments_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return await list_approved_comments(db, post.id)


@router.post("/posts/{slug}/comments", response_model=BlogCommentOut)
async def public_post_add_comment(
    slug: str,
    body: BlogCommentCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    await limiter.check_blog_comment_limit(client_ip(request))
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published" or not post.comments_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Комментарии отключены")
    comment = await add_comment(db, post, author_name=body.author_name, body=body.body)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/posts/{slug}")
async def public_post(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        redirect_post = await resolve_slug_redirect(db, slug)
        if redirect_post and redirect_post.status == "published":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "redirect", "slug": redirect_post.slug},
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return post_to_public(post)


@router.get("/media/{media_id}")
async def public_blog_media(media_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(BlogMedia, media_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    data = load_blog_image(row.storage_key)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return Response(
        content=data,
        media_type=row.mime_type or mime_for_ext("webp"),
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.get("/posts/{slug}/related")
async def public_post_related(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Похожие статьи по категории (до 4 шт.)."""
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    related = await get_related_posts(db, post, limit=4)
    return [
        {
            "id": p.id,
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt,
            "published_at": p.published_at,
            "reading_time_min": p.reading_time_min,
            "view_count": p.view_count or 0,
            "tags": p.tags or [],
            "category": p.category,
            "cover_image": media_out(p.cover_image),
        }
        for p in related
    ]


@router.get("/posts/{slug}/neighbors")
async def public_post_neighbors(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Предыдущая и следующая статья."""
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    prev_post, next_post = await get_neighbor_posts(db, post)

    def _minimal(p: BlogPost | None) -> dict | None:
        if not p:
            return None
        return {
            "slug": p.slug,
            "title": p.title,
            "cover_image": media_out(p.cover_image),
        }

    return {"prev": _minimal(prev_post), "next": _minimal(next_post)}


@router.post("/posts/{slug}/helpful", status_code=status.HTTP_204_NO_CONTENT)
async def public_post_helpful(
    slug: str,
    request: Request,
    vote: str = Query(description="yes or no"),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    redis=Depends(get_redis),
):
    """Голос «Была ли статья полезна?» (дедупликация по IP, 7 дней)."""
    if vote not in ("yes", "no"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="vote must be yes or no")
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        return

    ip = client_ip(request)
    dedup_key = f"blog:helpful_ip:{post.id}:{ip}"
    already = await redis.set(dedup_key, vote, nx=True, ex=7 * 86400)
    if not already:
        return  # уже голосовал

    col = BlogPost.helpful_yes if vote == "yes" else BlogPost.helpful_no
    await db.execute(update(BlogPost).where(BlogPost.id == post.id).values({col: col + 1}))
    await db.commit()


@router.get("/posts/{slug}/helpful")
async def public_post_helpful_stats(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Счётчики голосов helpful."""
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"yes": post.helpful_yes or 0, "no": post.helpful_no or 0}


@router.get("/sitemap.xml")
async def blog_sitemap(db: Annotated[AsyncSession, Depends(get_db)]):
    posts, _ = await list_posts_public(db, limit=500)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url><loc>https://glosix.ru/blog</loc><changefreq>daily</changefreq><priority>0.8</priority></url>",
    ]
    for post in posts:
        loc = f"https://glosix.ru/blog/{post.slug}"
        updated = post.updated_at.strftime("%Y-%m-%d") if post.updated_at else ""
        lines.append(f"  <url><loc>{loc}</loc><lastmod>{updated}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>")
    lines.append("</urlset>")
    body = "\n".join(lines)
    return Response(content=body, media_type="application/xml")
