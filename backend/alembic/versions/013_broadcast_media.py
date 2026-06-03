"""broadcasts: optional image/video attachment for MAX

Revision ID: 013_broadcast_media
Revises: 012_message_attachments
Create Date: 2026-05-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_broadcast_media"
down_revision: Union[str, None] = "012_message_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcasts",
        sa.Column("media_type", sa.String(length=16), nullable=False, server_default="none"),
    )
    op.add_column("broadcasts", sa.Column("media_token", sa.Text(), nullable=True))
    op.add_column("broadcasts", sa.Column("media_filename", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("broadcasts", "media_filename")
    op.drop_column("broadcasts", "media_token")
    op.drop_column("broadcasts", "media_type")
