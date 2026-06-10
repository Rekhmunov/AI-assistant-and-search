import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BlogCategory(Base):
    __tablename__ = "blog_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posts: Mapped[list["BlogPost"]] = relationship(back_populates="category")


class BlogMedia(Base):
    __tablename__ = "blog_media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/webp")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str] = mapped_column(String(512), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="inline")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True
    )
    cover_image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blog_media.id", ondelete="SET NULL"), nullable=True
    )
    og_image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blog_media.id", ondelete="SET NULL"), nullable=True
    )
    author_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reading_time_min: Mapped[int] = mapped_column(Integer, default=1)
    meta_title: Mapped[str] = mapped_column(String(255), default="")
    meta_description: Mapped[str] = mapped_column(String(500), default="")
    meta_keywords: Mapped[str] = mapped_column(String(500), default="")
    og_title: Mapped[str] = mapped_column(String(255), default="")
    og_description: Mapped[str] = mapped_column(String(500), default="")
    robots_index: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[BlogCategory | None] = relationship(back_populates="posts")
    cover_image: Mapped[BlogMedia | None] = relationship(foreign_keys=[cover_image_id])
    og_image: Mapped[BlogMedia | None] = relationship(foreign_keys=[og_image_id])


class BlogSlugRedirect(Base):
    __tablename__ = "blog_slug_redirects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    old_slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
