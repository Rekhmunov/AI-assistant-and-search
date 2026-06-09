"""uploaded_files.export_content_hash for export dedupe

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column("export_content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_uploaded_files_export_dedupe",
        "uploaded_files",
        ["user_id", "export_content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_export_dedupe", table_name="uploaded_files")
    op.drop_column("uploaded_files", "export_content_hash")
