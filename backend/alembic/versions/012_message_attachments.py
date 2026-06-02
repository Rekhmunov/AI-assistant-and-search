"""messages.attachments JSONB for user message file chips

Revision ID: 012_message_attachments
Revises: 011_message_images
Create Date: 2026-06-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_message_attachments"
down_revision: Union[str, None] = "011_message_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("attachments", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "attachments")
