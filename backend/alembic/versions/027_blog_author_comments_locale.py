"""blog author, comments, locale, slug per locale

Revision ID: 027
Revises: 026
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("blog_posts", sa.Column("author_name", sa.String(length=255), server_default="", nullable=False))
    op.add_column("blog_posts", sa.Column("comments_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("blog_posts", sa.Column("locale", sa.String(length=8), server_default="ru", nullable=False))
    op.create_index("ix_blog_posts_locale", "blog_posts", ["locale"])

    op.drop_constraint("uq_blog_posts_slug", "blog_posts", type_="unique")
    op.create_unique_constraint("uq_blog_posts_slug_locale", "blog_posts", ["slug", "locale"])

    op.create_table(
        "blog_comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", UUID(as_uuid=True), sa.ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="approved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_blog_comments_post_id", "blog_comments", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_blog_comments_post_id", table_name="blog_comments")
    op.drop_table("blog_comments")
    op.drop_constraint("uq_blog_posts_slug_locale", "blog_posts", type_="unique")
    op.create_unique_constraint("uq_blog_posts_slug", "blog_posts", ["slug"])
    op.drop_index("ix_blog_posts_locale", table_name="blog_posts")
    op.drop_column("blog_posts", "locale")
    op.drop_column("blog_posts", "comments_enabled")
    op.drop_column("blog_posts", "author_name")
