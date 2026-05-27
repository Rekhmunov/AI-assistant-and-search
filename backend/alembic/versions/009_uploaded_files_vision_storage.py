"""uploaded_files: media_kind + storage_key for vision attachments

Revision ID: 009
Revises: 008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column("media_kind", sa.String(16), nullable=False, server_default="document"),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("storage_key", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("uploaded_files", "storage_key")
    op.drop_column("uploaded_files", "media_kind")
