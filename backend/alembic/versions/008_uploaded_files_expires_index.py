"""index uploaded_files.expires_at for cleanup

Revision ID: 008
Revises: 007
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_uploaded_files_expires_at", "uploaded_files", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_expires_at", table_name="uploaded_files")
