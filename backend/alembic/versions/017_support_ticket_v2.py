"""support tickets v2: in_progress, payment context, replies

Revision ID: 017_support_ticket_v2
Revises: 016_support_tickets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "017_support_ticket_v2"
down_revision: Union[str, None] = "016_support_tickets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE support_ticket_status_enum ADD VALUE IF NOT EXISTS 'in_progress'")

    op.add_column("support_tickets", sa.Column("yookassa_payment_id", sa.String(length=128), nullable=True))
    op.add_column("support_tickets", sa.Column("payment_amount_rub", sa.Integer(), nullable=True))
    op.add_column(
        "support_tickets",
        sa.Column("subscription_id", UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "support_ticket_replies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            UUID(as_uuid=True),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_type", sa.String(length=16), nullable=False),
        sa.Column(
            "admin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("admin_email", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_support_ticket_replies_ticket_id", "support_ticket_replies", ["ticket_id"])


def downgrade() -> None:
    op.drop_table("support_ticket_replies")
    op.drop_column("support_tickets", "subscription_id")
    op.drop_column("support_tickets", "payment_amount_rub")
    op.drop_column("support_tickets", "yookassa_payment_id")
