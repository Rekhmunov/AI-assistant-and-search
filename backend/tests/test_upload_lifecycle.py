from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.uploaded_file import UploadedFile
from app.services.upload_lifecycle import _attachment_file_ids, is_file_expired


def test_is_file_expired():
    row = UploadedFile(
        id=uuid4(),
        user_id=uuid4(),
        filename="a.md",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert is_file_expired(row) is True


def test_attachment_file_ids_skips_markdown_document():
    ids = _attachment_file_ids(
        [
            {"id": str(uuid4()), "kind": "document"},
            {"kind": "markdown_document", "content": "# x"},
        ]
    )
    assert len(ids) == 1
