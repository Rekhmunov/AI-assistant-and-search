"""guest session keys for anonymous search

Revision ID: 005
Revises: 004
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("guest_key", sa.String(64), nullable=True))
    op.create_index("ix_users_guest_key", "users", ["guest_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_guest_key", table_name="users")
    op.drop_column("users", "guest_key")
