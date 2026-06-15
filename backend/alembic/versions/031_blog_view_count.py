"""blog post view_count

Revision ID: 031
Revises: 030
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "blog_posts",
        sa.Column("view_count", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("blog_posts", "view_count")
