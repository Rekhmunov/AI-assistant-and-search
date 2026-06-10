"""blog posts, categories, media

Revision ID: 026
Revises: 025
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_blog_categories_slug"),
    )
    op.create_index("ix_blog_categories_slug", "blog_categories", ["slug"])

    op.create_table(
        "blog_media",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=64), server_default="image/webp", nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.String(length=512), server_default="", nullable=False),
        sa.Column("purpose", sa.String(length=32), server_default="inline", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_admin_id", UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "blog_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("excerpt", sa.Text(), server_default="", nullable=False),
        sa.Column("content_html", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cover_image_id", UUID(as_uuid=True), sa.ForeignKey("blog_media.id", ondelete="SET NULL"), nullable=True),
        sa.Column("og_image_id", UUID(as_uuid=True), sa.ForeignKey("blog_media.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_admin_id", UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reading_time_min", sa.Integer(), server_default="1", nullable=False),
        sa.Column("meta_title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("meta_description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("meta_keywords", sa.String(length=500), server_default="", nullable=False),
        sa.Column("og_title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("og_description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("robots_index", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_blog_posts_slug"),
    )
    op.create_index("ix_blog_posts_slug", "blog_posts", ["slug"])
    op.create_index("ix_blog_posts_status", "blog_posts", ["status"])
    op.create_index("ix_blog_posts_published_at", "blog_posts", ["published_at"])

    op.create_table(
        "blog_slug_redirects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("old_slug", sa.String(length=200), nullable=False),
        sa.Column("post_id", UUID(as_uuid=True), sa.ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("old_slug", name="uq_blog_slug_redirects_old_slug"),
    )
    op.create_index("ix_blog_slug_redirects_old_slug", "blog_slug_redirects", ["old_slug"])


def downgrade() -> None:
    op.drop_table("blog_slug_redirects")
    op.drop_table("blog_posts")
    op.drop_table("blog_media")
    op.drop_table("blog_categories")
