"""blog tags and scheduled publish_at

Revision ID: 032
Revises: 031
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tags: JSON array of strings, e.g. ["SEO","ИИ","поиск"]
    op.add_column(
        "blog_posts",
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
    )
    # publish_at: optional scheduled publish timestamp (status='scheduled')
    op.add_column(
        "blog_posts",
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
    )
    # helpful_yes / helpful_no counters (no per-user tracking needed)
    op.add_column(
        "blog_posts",
        sa.Column("helpful_yes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "blog_posts",
        sa.Column("helpful_no", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("blog_posts", "helpful_no")
    op.drop_column("blog_posts", "helpful_yes")
    op.drop_column("blog_posts", "publish_at")
    op.drop_column("blog_posts", "tags")
