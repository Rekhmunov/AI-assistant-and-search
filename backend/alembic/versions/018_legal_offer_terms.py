"""seed offer and terms legal documents

Revision ID: 018_legal_offer_terms
Revises: 017_support_ticket_v2
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018_legal_offer_terms"
down_revision: Union[str, None] = "017_support_ticket_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.execute(
        "UPDATE legal_documents SET current_version_id = NULL WHERE slug IN ('offer', 'terms')"
    )
    op.execute(
        """
        DELETE FROM legal_document_versions
        WHERE document_id IN (
          SELECT id FROM legal_documents WHERE slug IN ('offer', 'terms')
        )
        """
    )
    op.execute("DELETE FROM legal_documents WHERE slug IN ('offer', 'terms')")
