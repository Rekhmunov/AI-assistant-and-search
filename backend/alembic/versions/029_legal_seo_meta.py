"""legal_seo_meta

Revision ID: 029
Revises: 028
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legal_documents", sa.Column("meta_title", sa.String(255), nullable=True))
    op.add_column("legal_documents", sa.Column("meta_description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("legal_documents", "meta_description")
    op.drop_column("legal_documents", "meta_title")
