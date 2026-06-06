"""legal documents with versioning and user consents

Revision ID: 014_legal_documents
Revises: 013_broadcast_media
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "014_legal_documents"
down_revision: Union[str, None] = "013_broadcast_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("public_path", sa.String(length=255), nullable=False),
        sa.Column("current_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_legal_documents_slug"),
        sa.UniqueConstraint("public_path", name="uq_legal_documents_public_path"),
    )
    op.create_index("ix_legal_documents_slug", "legal_documents", ["slug"])

    op.create_table(
        "legal_document_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("legal_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_admin_id", UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("admin_email", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_legal_document_versions_document_id", "legal_document_versions", ["document_id"])

    op.create_foreign_key(
        "fk_legal_documents_current_version",
        "legal_documents",
        "legal_document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "user_legal_consents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("legal_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("legal_document_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "document_id", name="uq_user_legal_consents_user_document"),
    )
    op.create_index("ix_user_legal_consents_user_id", "user_legal_consents", ["user_id"])

    # Seed default documents (empty content; admin fills in)
    op.execute(
        """
        INSERT INTO legal_documents (id, slug, title, public_path) VALUES
        ('11111111-1111-4111-8111-111111111101', 'privacy', 'Политика конфиденциальности', '/privacy'),
        ('11111111-1111-4111-8111-111111111102', 'pd_consent', 'Согласие на обработку персональных данных', '/consent-personal-data'),
        ('11111111-1111-4111-8111-111111111103', 'cookies', 'Политика использования cookie', '/cookies')
        """
    )
    op.execute(
        """
        INSERT INTO legal_document_versions (id, document_id, version_number, content_html) VALUES
        ('22222222-2222-4222-8222-222222222201', '11111111-1111-4111-8111-111111111101', 1, '<p></p>'),
        ('22222222-2222-4222-8222-222222222202', '11111111-1111-4111-8111-111111111102', 1, '<p></p>'),
        ('22222222-2222-4222-8222-222222222203', '11111111-1111-4111-8111-111111111103', 1, '<p></p>')
        """
    )
    op.execute(
        """
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222201' WHERE slug = 'privacy';
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222202' WHERE slug = 'pd_consent';
        UPDATE legal_documents SET current_version_id = '22222222-2222-4222-8222-222222222203' WHERE slug = 'cookies';
        """
    )


def downgrade() -> None:
    op.drop_table("user_legal_consents")
    op.drop_constraint("fk_legal_documents_current_version", "legal_documents", type_="foreignkey")
    op.drop_table("legal_document_versions")
    op.drop_table("legal_documents")
