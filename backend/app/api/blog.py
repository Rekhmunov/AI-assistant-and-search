from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_rate_limiter
from app.core.auth_limits import client_ip
from app.core.limiter import RateLimiter
from app.models.blog import BlogMedia
from app.schemas.blog import BlogCategoryOut, BlogCommentCreate, BlogCommentOut, BlogPostListItem
from app.services.blog_comments import add_comment, list_approved_comments
from app.services.blog_posts import (
    DEFAULT_LOCALE,
    blog_media_url,
    get_category_by_slug,
    get_post_by_slug,
    list_categories,
    list_posts_public,
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
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
):
    posts, _ = await list_posts_public(db, category_slug=category, offset=offset, limit=limit)
    return [
        {
            "id": p.id,
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt,
            "published_at": p.published_at,
            "reading_time_min": p.reading_time_min,
            "category": p.category,
            "cover_image": media_out(p.cover_image),
        }
        for p in posts
    ]


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
