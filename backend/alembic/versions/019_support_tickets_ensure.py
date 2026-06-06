"""ensure support tickets schema exists on older deploys

Revision ID: 019_support_tickets_ensure
Revises: 018_legal_offer_terms
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "019_support_tickets_ensure"
down_revision: Union[str, None] = "018_legal_offer_terms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "support_tickets" not in tables:
        op.execute(
            """
            DO $$ BEGIN
                CREATE TYPE support_ticket_status_enum AS ENUM ('open', 'closed');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                user_email VARCHAR(255),
                user_max_user_id BIGINT,
                source VARCHAR(64) NOT NULL DEFAULT 'general',
                message TEXT NOT NULL,
                status support_ticket_status_enum NOT NULL DEFAULT 'open',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                closed_at TIMESTAMPTZ,
                closed_by_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
                yookassa_payment_id VARCHAR(128),
                payment_amount_rub INTEGER,
                subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL
            )
            """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets (user_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets (status)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_created_at ON support_tickets (created_at)")
    else:
        op.execute(
            """
            DO $$ BEGIN
                CREATE TYPE support_ticket_status_enum AS ENUM ('open', 'closed');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
        columns = _table_columns("support_tickets")
        if "yookassa_payment_id" not in columns:
            op.add_column("support_tickets", sa.Column("yookassa_payment_id", sa.String(length=128), nullable=True))
        if "payment_amount_rub" not in columns:
            op.add_column("support_tickets", sa.Column("payment_amount_rub", sa.Integer(), nullable=True))
        if "subscription_id" not in columns:
            op.add_column(
                "support_tickets",
                sa.Column(
                    "subscription_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

    op.execute("ALTER TYPE support_ticket_status_enum ADD VALUE IF NOT EXISTS 'in_progress'")

    inspector = sa.inspect(bind)
    if "support_ticket_replies" not in inspector.get_table_names():
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
    pass
