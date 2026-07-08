"""Таблица service_incidents для долгосрочного хранения инцидентов внешних сервисов

Revision ID: 034_service_incidents
Revises: 033_offer_pro_999_credits
"""

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "service_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_service_incidents_service", "service_incidents", ["service"])
    op.create_index("ix_service_incidents_provider", "service_incidents", ["provider"])
    op.create_index("ix_service_incidents_occurred_at", "service_incidents", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("service_incidents")
