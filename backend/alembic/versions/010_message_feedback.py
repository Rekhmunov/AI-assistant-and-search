"""message_feedback: оценки ответов

Revision ID: 010_message_feedback
Revises: 009_uploaded_files_vision_storage
Create Date: 2026-05-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_message_feedback"
down_revision: Union[str, None] = "009_uploaded_files_vision_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    rating_enum = postgresql.ENUM("up", "down", name="message_feedback_rating_enum", create_type=False)
    rating_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "message_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("rating", rating_enum, nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_feedback_user"),
    )
    op.create_index("ix_message_feedback_message_id", "message_feedback", ["message_id"])
    op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])
    op.create_index("ix_message_feedback_created_at", "message_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_created_at", table_name="message_feedback")
    op.drop_index("ix_message_feedback_user_id", table_name="message_feedback")
    op.drop_index("ix_message_feedback_message_id", table_name="message_feedback")
    op.drop_table("message_feedback")
    op.execute("DROP TYPE IF EXISTS message_feedback_rating_enum")
