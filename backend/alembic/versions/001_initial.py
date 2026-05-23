"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE plan_enum AS ENUM ('free', 'pro')")
    op.execute("CREATE TYPE message_role_enum AS ENUM ('user', 'assistant')")
    op.execute("CREATE TYPE subscription_status_enum AS ENUM ('pending', 'active', 'canceled', 'failed')")
    op.execute("CREATE TYPE broadcast_audience_enum AS ENUM ('all', 'free', 'pro')")
    op.execute("CREATE TYPE broadcast_status_enum AS ENUM ('draft', 'sending', 'done', 'failed')")
    op.execute("CREATE TYPE broadcast_log_status_enum AS ENUM ('sent', 'failed')")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("language", sa.String(8), server_default="ru"),
        sa.Column("plan", postgresql.ENUM("free", "pro", name="plan_enum", create_type=False), server_default="free"),
        sa.Column("plan_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_max_user_id", "users", ["max_user_id"], unique=True)

    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("is_saved", sa.Boolean(), server_default="false"),
        sa.Column("message_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_threads_user_last", "threads", ["user_id", "last_message_at"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE")),
        sa.Column(
            "role",
            postgresql.ENUM("user", "assistant", name="message_role_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("follow_up_questions", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("yookassa_payment_id", sa.String(128), unique=True, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "active", "canceled", "failed", name="subscription_status_enum", create_type=False
            ),
            server_default="pending",
        ),
        sa.Column("amount_rub", sa.Integer(), server_default="299"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "audience",
            postgresql.ENUM("all", "free", "pro", name="broadcast_audience_enum", create_type=False),
            server_default="all",
        ),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "sending", "done", "failed", name="broadcast_status_enum", create_type=False),
            server_default="draft",
        ),
        sa.Column("sent_count", sa.Integer(), server_default="0"),
        sa.Column("failed_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "broadcast_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("broadcast_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcasts.id", ondelete="CASCADE")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "status",
            postgresql.ENUM("sent", "failed", name="broadcast_log_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("broadcast_logs")
    op.drop_table("broadcasts")
    op.drop_table("subscriptions")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("users")
    op.execute("DROP TYPE broadcast_log_status_enum")
    op.execute("DROP TYPE broadcast_status_enum")
    op.execute("DROP TYPE broadcast_audience_enum")
    op.execute("DROP TYPE subscription_status_enum")
    op.execute("DROP TYPE message_role_enum")
    op.execute("DROP TYPE plan_enum")
