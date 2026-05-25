"""query → URL memory (level 2 index)

Revision ID: 007
Revises: 006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_url_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("query_key", sa.String(length=64), nullable=False),
        sa.Column("normalized_query", sa.String(length=512), nullable=False),
        sa.Column("url_hash", sa.String(length=40), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_key", "url_hash", name="uq_query_url_log_key_url"),
    )
    op.create_index("ix_query_url_log_query_key", "query_url_log", ["query_key"])
    op.create_index("ix_query_url_log_last_used", "query_url_log", ["last_used_at"])


def downgrade() -> None:
    op.drop_index("ix_query_url_log_last_used", table_name="query_url_log")
    op.drop_index("ix_query_url_log_query_key", table_name="query_url_log")
    op.drop_table("query_url_log")
