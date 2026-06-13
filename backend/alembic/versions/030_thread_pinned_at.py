"""thread_pinned_at

Revision ID: 030
Revises: 029
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_threads_pinned_at", "threads", ["pinned_at"])


def downgrade() -> None:
    op.drop_index("ix_threads_pinned_at", table_name="threads")
    op.drop_column("threads", "pinned_at")
