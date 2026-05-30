"""messages.images JSONB for entity image gallery

Revision ID: 011_message_images
Revises: 010_message_feedback
Create Date: 2026-05-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_message_images"
down_revision: Union[str, None] = "010_message_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("images", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "images")
