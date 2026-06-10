from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.models.blog import BlogCategory, BlogMedia, BlogPost
from app.schemas.blog import (
    BlogCategoryCreate,
    BlogCategoryOut,
    BlogCategoryUpdate,
    BlogGenerateArticleIn,
    BlogGenerateArticleOut,
    BlogGenerateCoverIn,
    BlogGenerateCoverOut,
    BlogGenerateMetaIn,
    BlogGenerateMetaOut,
    BlogMediaUploadOut,
    BlogPostAdminOut,
    BlogPostCreate,
    BlogPostUpdate,
)
from app.services.admin_audit import log_admin_action
from app.services.blog_ai import (
    generate_blog_article,
    generate_blog_cover,
    generate_blog_inline_image,
    media_upload_out,
)
from app.services.blog_seo_meta import VALID_META_FIELDS, generate_blog_meta_field
from app.services.gigachat_image_gen import ImageGenerationError
from app.services.blog_image import ALLOWED_UPLOAD_MIME, process_blog_image
from app.services.blog_posts import (
    create_post,
    list_categories,
    list_posts_admin,
    post_to_admin,
    update_post,
)
from app.services.blog_slug import ensure_unique_category_slug, ensure_unique_post_slug, is_valid_slug, slugify_title
from app.services.blog_comments import delete_comment, list_post_comments_admin
from app.services.blog_prerender import rebuild_all_prerender, refresh_blog_prerender_for_post
from app.services.blog_storage import save_blog_image
import redis.asyncio as redis

router = APIRouter(prefix="/blog", tags=["admin-blog"])


async def _load_post(db: AsyncSession, post_id: UUID) -> BlogPost:
    result = await db.execute(
        select(BlogPost)
        .where(BlogPost.id == post_id)
        .options(
            selectinload(BlogPost.category),
            selectinload(BlogPost.cover_image),
            selectinload(BlogPost.og_image),
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return post


@router.get("/categories", response_model=list[BlogCategoryOut])
async def admin_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("blog:read")),
):
    return await list_categories(db)


@router.post("/categories", response_model=BlogCategoryOut)
async def create_category(
    body: BlogCategoryCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    slug = (body.slug or "").strip() or slugify_title(body.name, max_len=80)
    if not is_valid_slug(slug):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный slug")
    slug = await ensure_unique_category_slug(db, slug)
    cat = BlogCategory(slug=slug, name=body.name.strip(), description=body.description.strip())
    db.add(cat)
    await log_admin_action(
        db,
        admin=admin,
        action="blog.category.create",
        resource_type="blog_category",
        resource_id=str(cat.id),
        details={"slug": slug},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/categories/{category_id}", response_model=BlogCategoryOut)
async def patch_category(
    category_id: UUID,
    body: BlogCategoryUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    cat = await db.get(BlogCategory, category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    if body.name is not None:
        cat.name = body.name.strip()
    if body.description is not None:
        cat.description = body.description.strip()
    if body.sort_order is not None:
        cat.sort_order = body.sort_order
    if body.slug is not None:
        slug = body.slug.strip()
        if not is_valid_slug(slug):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный slug")
        taken = await db.scalar(
            select(BlogCategory.id).where(BlogCategory.slug == slug, BlogCategory.id != category_id)
        )
        if taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug занят")
        cat.slug = slug
    await log_admin_action(
        db,
        admin=admin,
        action="blog.category.update",
        resource_type="blog_category",
        resource_id=str(category_id),
        details={},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    cat = await db.get(BlogCategory, category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    await db.delete(cat)
    await log_admin_action(
        db,
        admin=admin,
        action="blog.category.delete",
        resource_type="blog_category",
        resource_id=str(category_id),
        details={},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()


@router.get("/posts")
async def admin_list_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("blog:read")),
    status_filter: str | None = Query(default=None, alias="status"),
    category_id: UUID | None = None,
    search: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    posts, total = await list_posts_admin(
        db, status=status_filter, category_id=category_id, search=search, offset=offset, limit=limit
    )
    return {
        "items": [post_to_admin(p) for p in posts],
        "total": total,
    }


@router.get("/posts/{post_id}", response_model=BlogPostAdminOut)
async def admin_get_post(
    post_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("blog:read")),
):
    post = await _load_post(db, post_id)
    author_email = None
    if post.author_admin_id:
        author = await db.get(AdminUser, post.author_admin_id)
        author_email = author.email if author else None
    return post_to_admin(post, author_email=author_email)


@router.post("/posts", response_model=BlogPostAdminOut)
async def admin_create_post(
    body: BlogPostCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    try:
        post = await create_post(db, body.model_dump(), admin_id=admin.id)
    except ValueError as exc:
        if str(exc) == "invalid_slug":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный slug") from exc
        raise
    await log_admin_action(
        db,
        admin=admin,
        action="blog.post.create",
        resource_type="blog_post",
        resource_id=str(post.id),
        details={"slug": post.slug, "status": post.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    post = await _load_post(db, post.id)
    if post.status == "published":
        await refresh_blog_prerender_for_post(db, post)
    return post_to_admin(post, author_email=admin.email)


@router.patch("/posts/{post_id}", response_model=BlogPostAdminOut)
async def admin_update_post(
    post_id: UUID,
    body: BlogPostUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    post = await _load_post(db, post_id)
    try:
        await update_post(db, post, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        if str(exc) == "invalid_slug":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный slug") from exc
        raise
    await log_admin_action(
        db,
        admin=admin,
        action="blog.post.update",
        resource_type="blog_post",
        resource_id=str(post_id),
        details={"slug": post.slug, "status": post.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    post = await _load_post(db, post_id)
    await refresh_blog_prerender_for_post(db, post)
    return post_to_admin(post, author_email=admin.email)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_post(
    post_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    post = await _load_post(db, post_id)
    await db.delete(post)
    await log_admin_action(
        db,
        admin=admin,
        action="blog.post.delete",
        resource_type="blog_post",
        resource_id=str(post_id),
        details={"slug": post.slug},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await rebuild_all_prerender(db)


@router.get("/posts/{post_id}/comments")
async def admin_list_comments(
    post_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("blog:read")),
):
    await _load_post(db, post_id)
    return await list_post_comments_admin(db, post_id)


@router.delete("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_comment(
    post_id: UUID,
    comment_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    if not await delete_comment(db, comment_id, post_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Комментарий не найден")
    await log_admin_action(
        db,
        admin=admin,
        action="blog.comment.delete",
        resource_type="blog_comment",
        resource_id=str(comment_id),
        details={"post_id": str(post_id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()


@router.post("/rebuild-prerender")
async def admin_rebuild_prerender(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    count = await rebuild_all_prerender(db)
    await log_admin_action(
        db,
        admin=admin,
        action="blog.prerender.rebuild",
        resource_type="blog",
        resource_id=None,
        details={"files": count},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"ok": True, "files": count}


@router.post("/media", response_model=BlogMediaUploadOut)
async def upload_blog_media(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
    file: UploadFile = File(...),
    purpose: str = Query(default="inline"),
    alt_text: str = Query(default=""),
):
    if purpose not in {"inline", "cover"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный purpose")
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_UPLOAD_MIME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Формат изображения не поддерживается")
    raw = await file.read()
    if not raw or len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой (макс. 15 МБ)")
    processed = process_blog_image(raw, purpose=purpose)
    media_id = uuid4()
    storage_key = save_blog_image(media_id, processed.data)
    media = BlogMedia(
        id=media_id,
        filename=(file.filename or f"image-{media_id.hex[:8]}.webp").rsplit(".", 1)[0] + ".webp",
        storage_key=storage_key,
        mime_type=processed.mime_type,
        size_bytes=len(processed.data),
        width=processed.width,
        height=processed.height,
        alt_text=alt_text.strip(),
        purpose=purpose,
        created_by_admin_id=admin.id,
    )
    db.add(media)
    await log_admin_action(
        db,
        admin=admin,
        action="blog.media.upload",
        resource_type="blog_media",
        resource_id=str(media_id),
        details={"size_bytes": media.size_bytes, "purpose": purpose},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return media_upload_out(media)


def _blog_ai_http_error(exc: Exception, *, kind: str) -> HTTPException:
    if isinstance(exc, ImageGenerationError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Не удалось сгенерировать {kind}: {exc}",
    )


@router.post("/generate-article", response_model=BlogGenerateArticleOut)
async def admin_generate_article(
    body: BlogGenerateArticleIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    try:
        result = await generate_blog_article(
            db,
            redis_client,
            topic=body.topic,
            requirements=body.requirements,
            fill_seo=body.fill_seo,
            generate_slug=body.generate_slug,
        )
        await log_admin_action(
            db,
            admin=admin,
            action="blog.ai.generate_article",
            resource_type="blog_post",
            resource_id=None,
            details={"topic": body.topic[:120]},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _blog_ai_http_error(exc, kind="статью") from exc


@router.post("/generate-cover", response_model=BlogGenerateCoverOut)
async def admin_generate_cover(
    body: BlogGenerateCoverIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    try:
        media = await generate_blog_cover(
            db,
            redis_client,
            prompt=body.prompt,
            alt_text=body.alt_text,
            admin_id=admin.id,
        )
        await log_admin_action(
            db,
            admin=admin,
            action="blog.ai.generate_cover",
            resource_type="blog_media",
            resource_id=str(media.id),
            details={"prompt": body.prompt[:120]},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        return {"media": media_upload_out(media)}
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _blog_ai_http_error(exc, kind="обложку") from exc


@router.post("/generate-inline-image", response_model=BlogGenerateCoverOut)
async def admin_generate_inline_image(
    body: BlogGenerateCoverIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    try:
        media = await generate_blog_inline_image(
            db,
            redis_client,
            prompt=body.prompt,
            alt_text=body.alt_text,
            admin_id=admin.id,
        )
        await log_admin_action(
            db,
            admin=admin,
            action="blog.ai.generate_inline_image",
            resource_type="blog_media",
            resource_id=str(media.id),
            details={"prompt": body.prompt[:120]},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        return {"media": media_upload_out(media)}
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _blog_ai_http_error(exc, kind="изображение") from exc


@router.post("/generate-meta", response_model=BlogGenerateMetaOut)
async def admin_generate_meta(
    body: BlogGenerateMetaIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    admin: Annotated[AdminUser, Depends(require_permission("blog:write"))],
):
    field = body.field.strip()
    if field not in VALID_META_FIELDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректное поле meta")
    try:
        result = await generate_blog_meta_field(
            db,
            redis_client,
            field=field,
            title=body.title,
            excerpt=body.excerpt,
            content_html=body.content_html,
        )
        await log_admin_action(
            db,
            admin=admin,
            action="blog.ai.generate_meta",
            resource_type="blog_post",
            resource_id=None,
            details={"field": field, "title": body.title[:80]},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _blog_ai_http_error(exc, kind="meta-тег") from exc
