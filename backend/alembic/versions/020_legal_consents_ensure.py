"""ensure legal consent audit columns and offer documents

Revision ID: 020_legal_consents_ensure
Revises: 019_support_tickets_ensure
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_legal_consents_ensure"
down_revision: Union[str, None] = "019_support_tickets_ensure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _consent_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_legal_consents" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("user_legal_consents")}


def upgrade() -> None:
    columns = _consent_columns()
    if columns:
        if "source" not in columns:
            op.add_column("user_legal_consents", sa.Column("source", sa.String(length=64), nullable=True))
        if "ip_address" not in columns:
            op.add_column("user_legal_consents", sa.Column("ip_address", sa.String(length=64), nullable=True))
        if "user_agent" not in columns:
            op.add_column("user_legal_consents", sa.Column("user_agent", sa.Text(), nullable=True))
        if "consent_method" not in columns:
            op.add_column("user_legal_consents", sa.Column("consent_method", sa.String(length=32), nullable=True))

    op.execute(
        """
        INSERT INTO legal_documents (id, slug, title, public_path)
        SELECT '11111111-1111-4111-8111-111111111104', 'offer', 'Публичная оферта', '/offer'
        WHERE NOT EXISTS (SELECT 1 FROM legal_documents WHERE slug = 'offer')
        """
    )
    op.execute(
        """
        INSERT INTO legal_documents (id, slug, title, public_path)
        SELECT '11111111-1111-4111-8111-111111111105', 'terms', 'Пользовательское соглашение', '/terms'
        WHERE NOT EXISTS (SELECT 1 FROM legal_documents WHERE slug = 'terms')
        """
    )
    op.execute(
        """
        INSERT INTO legal_document_versions (id, document_id, version_number, content_html)
        SELECT '22222222-2222-4222-8222-222222222204', '11111111-1111-4111-8111-111111111104', 1, '<p></p>'
        WHERE EXISTS (SELECT 1 FROM legal_documents WHERE slug = 'offer')
          AND NOT EXISTS (
            SELECT 1 FROM legal_document_versions v
            JOIN legal_documents d ON d.id = v.document_id
            WHERE d.slug = 'offer'
          )
        """
    )
    op.execute(
        """
        INSERT INTO legal_document_versions (id, document_id, version_number, content_html)
        SELECT '22222222-2222-4222-8222-222222222205', '11111111-1111-4111-8111-111111111105', 1, '<p></p>'
        WHERE EXISTS (SELECT 1 FROM legal_documents WHERE slug = 'terms')
          AND NOT EXISTS (
            SELECT 1 FROM legal_document_versions v
            JOIN legal_documents d ON d.id = v.document_id
            WHERE d.slug = 'terms'
          )
        """
    )
    op.execute(
        """
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222204'
        WHERE slug = 'offer' AND current_version_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222205'
        WHERE slug = 'terms' AND current_version_id IS NULL
        """
    )


def downgrade() -> None:
    pass
