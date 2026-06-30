"""Публичная оферта v2: тариф Pro 999 руб., система кредитов

Revision ID: 033_offer_pro_999_credits
Revises: 032_blog_tags_publish_at
"""

import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_offer_pro_999_credits"
down_revision: Union[str, None] = "032_blog_tags_publish_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Маркер новой версии — уникальная строка из нового текста
_NEW_MARKER = "999 (девятьсот девяносто девять) рублей"
_SLUG = "offer"


def _load_html() -> str:
    backend = Path(__file__).resolve().parents[2]
    return (backend / "app" / "data" / "legal" / "offer_ru.html").read_text(encoding="utf-8")


def _doc_id_by_slug(bind, slug: str) -> str | None:
    row = bind.execute(
        sa.text("SELECT id::text FROM legal_documents WHERE slug = :slug"),
        {"slug": slug},
    ).fetchone()
    return row[0] if row else None


def _version_exists(bind, slug: str, marker: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM legal_document_versions v
            JOIN legal_documents d ON d.id = v.document_id
            WHERE d.slug = :slug AND v.content_html LIKE :marker
            LIMIT 1
            """
        ),
        {"slug": slug, "marker": f"%{marker}%"},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    # Пропускаем если такая версия уже есть
    if _version_exists(bind, _SLUG, _NEW_MARKER):
        return

    doc_id = _doc_id_by_slug(bind, _SLUG)
    if not doc_id:
        # Документ ещё не создан (нестандартная БД) — пропускаем
        return

    content_html = _load_html()

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
        {"vid": version_id, "slug": _SLUG},
    )


def downgrade() -> None:
    bind = op.get_bind()

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
        {"slug": _SLUG, "marker": f"%{_NEW_MARKER}%"},
    ).fetchone()

    if not row:
        return

    version_id = row[0]
    doc_id = _doc_id_by_slug(bind, _SLUG)
    if not doc_id:
        return

    # Откатываемся на предыдущую версию
    prev = bind.execute(
        sa.text(
            """
            SELECT id::text FROM legal_document_versions
            WHERE document_id = :doc_id AND id::text != :vid
            ORDER BY version_number DESC
            LIMIT 1
            """
        ),
        {"doc_id": doc_id, "vid": version_id},
    ).fetchone()
    prev_id = prev[0] if prev else None

    bind.execute(
        sa.text("UPDATE legal_documents SET current_version_id = :vid WHERE slug = :slug"),
        {"vid": prev_id, "slug": _SLUG},
    )
    bind.execute(
        sa.text("DELETE FROM legal_document_versions WHERE id = :vid"),
        {"vid": version_id},
    )
