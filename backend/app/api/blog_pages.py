"""Prerendered HTML pages for /blog (SEO)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.blog_posts import (
    DEFAULT_LOCALE,
    get_category_by_slug,
    get_post_by_slug,
    list_posts_public,
    resolve_slug_redirect,
)
from app.services.blog_prerender import (
    read_prerender,
    render_category_html,
    render_index_html,
    render_post_html,
    save_post_prerender,
)

router = APIRouter(tags=["blog-pages"])


def _cache_headers() -> dict[str, str]:
    return {"Cache-Control": "public, max-age=300", "X-Prerender": "blog"}


@router.get("/blog/sitemap.xml")
async def blog_sitemap_page(db: Annotated[AsyncSession, Depends(get_db)]):
    from datetime import datetime, timezone
    from app.services.blog_categories import list_categories
    from app.services.legal_documents import list_documents_admin, ensure_default_documents

    posts, _ = await list_posts_public(db, limit=500)
    categories = await list_categories(db)
    await ensure_default_documents(db)
    legal_docs = await list_documents_admin(db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        # Главная
        f'  <url><loc>https://glosix.ru/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>',
        # Блог
        f'  <url><loc>https://glosix.ru/blog</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
    ]

    # Категории блога
    for cat in categories:
        lines.append(
            f'  <url><loc>https://glosix.ru/blog/category/{cat.slug}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>'
        )

    # Статьи блога
    for post in posts:
        loc = f"https://glosix.ru/blog/{post.slug}"
        updated = post.updated_at.strftime("%Y-%m-%d") if post.updated_at else today
        lines.append(
            f'  <url><loc>{loc}</loc><lastmod>{updated}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>'
        )

    # Юридические страницы
    legal_paths = {
        "/privacy": ("monthly", "0.4"),
        "/offer": ("monthly", "0.4"),
        "/cookies": ("monthly", "0.4"),
        "/terms": ("monthly", "0.4"),
        "/consent-personal-data": ("monthly", "0.3"),
    }
    for doc in legal_docs:
        if not doc.current_version_id:
            continue
        path = doc.public_path.lstrip("/")
        full_path = f"/{path}"
        freq, priority = legal_paths.get(full_path, ("monthly", "0.3"))
        updated = doc.updated_at.strftime("%Y-%m-%d") if doc.updated_at else today
        lines.append(
            f'  <url><loc>https://glosix.ru{full_path}</loc><lastmod>{updated}</lastmod><changefreq>{freq}</changefreq><priority>{priority}</priority></url>'
        )

    lines.append("</urlset>")
    body = "\n".join(lines)
    return Response(
        content=body,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/blog", response_class=HTMLResponse)
async def blog_index_page(db: Annotated[AsyncSession, Depends(get_db)]):
    cached = read_prerender(f"{DEFAULT_LOCALE}/index.html")
    if cached:
        return HTMLResponse(cached, headers=_cache_headers())
    html = await render_index_html(db)
    return HTMLResponse(html, headers=_cache_headers())


@router.get("/blog/category/{slug}", response_class=HTMLResponse)
async def blog_category_page(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    cat = await get_category_by_slug(db, slug)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    cached = read_prerender(f"{DEFAULT_LOCALE}/categories/{slug}.html")
    if cached:
        return HTMLResponse(cached, headers=_cache_headers())
    html = await render_category_html(db, cat)
    return HTMLResponse(html, headers=_cache_headers())


@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post_page(slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    if slug == "category":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    post = await get_post_by_slug(db, slug, locale=DEFAULT_LOCALE)
    if not post or post.status != "published":
        redirect_post = await resolve_slug_redirect(db, slug)
        if redirect_post and redirect_post.status == "published":
            return RedirectResponse(url=f"/blog/{redirect_post.slug}", status_code=301)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    cached = read_prerender(f"{DEFAULT_LOCALE}/posts/{slug}.html")
    if cached:
        return HTMLResponse(cached, headers=_cache_headers())
    html = await render_post_html(db, post)
    await save_post_prerender(db, post)
    return HTMLResponse(html, headers=_cache_headers())
