"""thread soft delete + message debug_trace for admin

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_threads_deleted_at", "threads", ["deleted_at"])
    op.add_column(
        "messages",
        sa.Column("debug_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "debug_trace")
    op.drop_index("ix_threads_deleted_at", table_name="threads")
    op.drop_column("threads", "deleted_at")
