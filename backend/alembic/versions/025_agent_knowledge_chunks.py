"""agent knowledge chunks for support assistants

Revision ID: 025
Revises: 024
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_knowledge_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_agent_knowledge_chunks_agent_id",
        "agent_knowledge_chunks",
        ["agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_knowledge_chunks_agent_id", table_name="agent_knowledge_chunks")
    op.drop_table("agent_knowledge_chunks")
