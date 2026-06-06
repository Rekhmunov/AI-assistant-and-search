"""legal consent audit fields

Revision ID: 015_legal_consent_audit
Revises: 014_legal_documents
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_legal_consent_audit"
down_revision: Union[str, None] = "014_legal_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_legal_consents", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("user_legal_consents", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("user_legal_consents", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column("user_legal_consents", sa.Column("consent_method", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("user_legal_consents", "consent_method")
    op.drop_column("user_legal_consents", "user_agent")
    op.drop_column("user_legal_consents", "ip_address")
    op.drop_column("user_legal_consents", "source")
