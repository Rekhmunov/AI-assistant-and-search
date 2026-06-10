"""Blog comments."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogComment, BlogPost


async def list_approved_comments(db: AsyncSession, post_id: UUID) -> list[BlogComment]:
    result = await db.execute(
        select(BlogComment)
        .where(BlogComment.post_id == post_id, BlogComment.status == "approved")
        .order_by(BlogComment.created_at.asc())
    )
    return list(result.scalars().all())


async def list_post_comments_admin(db: AsyncSession, post_id: UUID) -> list[BlogComment]:
    result = await db.execute(
        select(BlogComment).where(BlogComment.post_id == post_id).order_by(BlogComment.created_at.desc())
    )
    return list(result.scalars().all())


async def add_comment(
    db: AsyncSession,
    post: BlogPost,
    *,
    author_name: str,
    body: str,
) -> BlogComment:
    comment = BlogComment(
        post_id=post.id,
        author_name=author_name.strip(),
        body=body.strip(),
        status="approved",
    )
    db.add(comment)
    await db.flush()
    return comment


async def delete_comment(db: AsyncSession, comment_id: UUID, post_id: UUID) -> bool:
    row = await db.get(BlogComment, comment_id)
    if not row or row.post_id != post_id:
        return False
    await db.delete(row)
    await db.flush()
    return True
