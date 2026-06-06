"""support_tickets.user_last_read_at for unread admin replies

Revision ID: 021_support_ticket_user_read
Revises: 020_legal_consents_ensure
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_support_ticket_user_read"
down_revision: Union[str, None] = "020_legal_consents_ensure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("support_tickets", "user_last_read_at"):
        op.add_column(
            "support_tickets",
            sa.Column("user_last_read_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _has_column("support_tickets", "user_last_read_at"):
        op.drop_column("support_tickets", "user_last_read_at")
