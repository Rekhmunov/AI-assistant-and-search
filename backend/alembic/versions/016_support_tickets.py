"""support tickets

Revision ID: 016_support_tickets
Revises: 015_legal_consent_audit
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016_support_tickets"
down_revision: Union[str, None] = "015_legal_consent_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
            closed_by_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_created_at ON support_tickets (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support_tickets")
    op.execute("DROP TYPE IF EXISTS support_ticket_status_enum")
