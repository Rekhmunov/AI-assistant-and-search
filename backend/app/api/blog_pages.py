"""Prerendered HTML pages for /blog (SEO)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.blog_posts import DEFAULT_LOCALE, get_category_by_slug, get_post_by_slug, resolve_slug_redirect
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
