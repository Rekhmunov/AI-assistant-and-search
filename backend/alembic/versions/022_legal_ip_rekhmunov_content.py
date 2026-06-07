"""legal offer and pd consent content for IP Rekhmunov

Revision ID: 022_legal_ip_rekhmunov
Revises: 021_support_ticket_user_read
"""

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_legal_ip_rekhmunov"
down_revision: Union[str, None] = "021_support_ticket_user_read"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OFFER_DOC_ID = "11111111-1111-4111-8111-111111111104"
PD_DOC_ID = "11111111-1111-4111-8111-111111111102"
OFFER_VERSION_ID = "22222222-2222-4222-8222-222222222206"
PD_VERSION_ID = "22222222-2222-4222-8222-222222222207"


def _load_html(filename: str) -> str:
    backend = Path(__file__).resolve().parents[2]
    return (backend / "app" / "data" / "legal" / filename).read_text(encoding="utf-8")


def _insert_version(doc_id: str, version_id: str, version_number: int, content_html: str) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO legal_document_versions (id, document_id, version_number, content_html)
            VALUES (:id, :doc_id, :ver, :html)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": version_id, "doc_id": doc_id, "ver": version_number, "html": content_html},
    )


def upgrade() -> None:
    offer_html = _load_html("offer_ru.html")
    pd_html = _load_html("pd_consent_ru.html")

    _insert_version(OFFER_DOC_ID, OFFER_VERSION_ID, 2, offer_html)
    _insert_version(PD_DOC_ID, PD_VERSION_ID, 2, pd_html)

    op.execute(
        f"""
        UPDATE legal_documents SET current_version_id = '{OFFER_VERSION_ID}'
        WHERE slug = 'offer'
        """
    )
    op.execute(
        f"""
        UPDATE legal_documents SET current_version_id = '{PD_VERSION_ID}'
        WHERE slug = 'pd_consent'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222204'
        WHERE slug = 'offer'
        """
    )
    op.execute(
        f"""
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222202'
        WHERE slug = 'pd_consent'
        """
    )
    op.execute(
        f"DELETE FROM legal_document_versions WHERE id IN ('{OFFER_VERSION_ID}', '{PD_VERSION_ID}')"
    )
