"""legal offer and pd consent content for IP Rekhmunov

Revision ID: 022_legal_ip_rekhmunov
Revises: 021_support_ticket_user_read
"""

import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_legal_ip_rekhmunov"
down_revision: Union[str, None] = "021_support_ticket_user_read"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Маркер уже применённой миграции (ИНН в тексте документов).
_CONTENT_MARKER = "372400681880"

_DOCUMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("offer", "Публичная оферта", "/offer", "offer_ru.html"),
    ("pd_consent", "Согласие на обработку персональных данных", "/consent-personal-data", "pd_consent_ru.html"),
)


def _load_html(filename: str) -> str:
    backend = Path(__file__).resolve().parents[2]
    return (backend / "app" / "data" / "legal" / filename).read_text(encoding="utf-8")


def _doc_id_by_slug(bind, slug: str) -> str | None:
    row = bind.execute(
        sa.text("SELECT id::text FROM legal_documents WHERE slug = :slug"),
        {"slug": slug},
    ).fetchone()
    return row[0] if row else None


def _ensure_document(bind, slug: str, title: str, public_path: str) -> str:
    doc_id = _doc_id_by_slug(bind, slug)
    if doc_id:
        return doc_id

    doc_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            """
            INSERT INTO legal_documents (id, slug, title, public_path)
            VALUES (:id, :slug, :title, :path)
            """
        ),
        {"id": doc_id, "slug": slug, "title": title, "path": public_path},
    )
    return doc_id


def _ensure_empty_v1(bind, doc_id: str) -> None:
    count = bind.execute(
        sa.text("SELECT COUNT(*) FROM legal_document_versions WHERE document_id = :doc_id"),
        {"doc_id": doc_id},
    ).scalar_one()
    if int(count or 0) > 0:
        return

    version_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            """
            INSERT INTO legal_document_versions (id, document_id, version_number, content_html)
            VALUES (:id, :doc_id, 1, '<p></p>')
            """
        ),
        {"id": version_id, "doc_id": doc_id},
    )
    bind.execute(
        sa.text("UPDATE legal_documents SET current_version_id = :vid WHERE id = :doc_id"),
        {"vid": version_id, "doc_id": doc_id},
    )


def _find_version_with_marker(bind, slug: str) -> str | None:
    row = bind.execute(
        sa.text(
            """
            SELECT v.id::text
            FROM legal_document_versions v
            JOIN legal_documents d ON d.id = v.document_id
            WHERE d.slug = :slug AND v.content_html LIKE :marker
            ORDER BY v.version_number DESC
            LIMIT 1
            """
        ),
        {"slug": slug, "marker": f"%{_CONTENT_MARKER}%"},
    ).fetchone()
    return row[0] if row else None


def _publish_version(bind, slug: str, title: str, public_path: str, content_html: str) -> None:
    existing_id = _find_version_with_marker(bind, slug)
    if existing_id:
        bind.execute(
            sa.text("UPDATE legal_documents SET current_version_id = :vid WHERE slug = :slug"),
            {"vid": existing_id, "slug": slug},
        )
        return

    doc_id = _ensure_document(bind, slug, title, public_path)
    _ensure_empty_v1(bind, doc_id)

    max_ver = bind.execute(
        sa.text(
            "SELECT COALESCE(MAX(version_number), 0) FROM legal_document_versions WHERE document_id = :doc_id"
        ),
        {"doc_id": doc_id},
    ).scalar_one()
    version_id = str(uuid.uuid4())
    next_ver = int(max_ver or 0) + 1

    bind.execute(
        sa.text(
            """
            INSERT INTO legal_document_versions (id, document_id, version_number, content_html)
            VALUES (:id, :doc_id, :ver, :html)
            """
        ),
        {"id": version_id, "doc_id": doc_id, "ver": next_ver, "html": content_html},
    )
    bind.execute(
        sa.text("UPDATE legal_documents SET current_version_id = :vid WHERE slug = :slug"),
        {"vid": version_id, "slug": slug},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, title, public_path, html_file in _DOCUMENTS:
        _publish_version(bind, slug, title, public_path, _load_html(html_file))


def downgrade() -> None:
    bind = op.get_bind()
    for slug, _, _, _ in _DOCUMENTS:
        version_id = _find_version_with_marker(bind, slug)
        if not version_id:
            continue

        doc_id = _doc_id_by_slug(bind, slug)
        if not doc_id:
            continue

        bind.execute(
            sa.text("DELETE FROM legal_document_versions WHERE id = :vid"),
            {"vid": version_id},
        )

        fallback = bind.execute(
            sa.text(
                """
                SELECT id::text FROM legal_document_versions
                WHERE document_id = :doc_id
                ORDER BY version_number DESC
                LIMIT 1
                """
            ),
            {"doc_id": doc_id},
        ).fetchone()
        fallback_id = fallback[0] if fallback else None
        bind.execute(
            sa.text("UPDATE legal_documents SET current_version_id = :vid WHERE id = :doc_id"),
            {"vid": fallback_id, "doc_id": doc_id},
        )
