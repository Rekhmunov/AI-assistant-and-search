"""agent activity logs for debugging

Revision ID: 028
Revises: 027
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_activity_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agent_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reminder_id", UUID(as_uuid=True), sa.ForeignKey("agent_reminders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_activity_logs_agent_id", "agent_activity_logs", ["agent_id"])
    op.create_index("ix_agent_activity_logs_thread_id", "agent_activity_logs", ["thread_id"])
    op.create_index("ix_agent_activity_logs_created_at", "agent_activity_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_activity_logs_created_at", table_name="agent_activity_logs")
    op.drop_index("ix_agent_activity_logs_thread_id", table_name="agent_activity_logs")
    op.drop_index("ix_agent_activity_logs_agent_id", table_name="agent_activity_logs")
    op.drop_table("agent_activity_logs")
