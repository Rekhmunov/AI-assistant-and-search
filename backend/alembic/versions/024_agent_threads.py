"""agent threads and reminder instances

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("thread_type", sa.String(16), nullable=False, server_default="search"),
    )
    op.add_column("threads", sa.Column("agent_seq", sa.Integer(), nullable=True))
    op.create_index("ix_threads_thread_type", "threads", ["thread_type"])

    op.create_table(
        "agent_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("instruction_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("max_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("unread_notice", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("thread_id", name="uq_agent_instances_thread_id"),
    )
    op.create_index("ix_agent_instances_user_id", "agent_instances", ["user_id"])
    op.create_index("ix_agent_instances_status", "agent_instances", ["status"])
    op.create_index("ix_agent_instances_max_user_id", "agent_instances", ["max_user_id"])

    op.create_table(
        "agent_reminders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agent_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("recurrence", sa.String(32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_reminders_run_at_status", "agent_reminders", ["run_at", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_reminders_run_at_status", table_name="agent_reminders")
    op.drop_table("agent_reminders")
    op.drop_index("ix_agent_instances_max_user_id", table_name="agent_instances")
    op.drop_index("ix_agent_instances_status", table_name="agent_instances")
    op.drop_index("ix_agent_instances_user_id", table_name="agent_instances")
    op.drop_table("agent_instances")
    op.drop_index("ix_threads_thread_type", table_name="threads")
    op.drop_column("threads", "agent_seq")
    op.drop_column("threads", "thread_type")
