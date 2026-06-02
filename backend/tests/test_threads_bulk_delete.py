import uuid

import pytest
from pydantic import ValidationError

from app.schemas.thread import ThreadBulkDeleteIn


def test_bulk_delete_schema_requires_at_least_one_id():
    with pytest.raises(ValidationError):
        ThreadBulkDeleteIn(thread_ids=[])


def test_bulk_delete_schema_max_100_ids():
    with pytest.raises(ValidationError):
        ThreadBulkDeleteIn(thread_ids=[uuid.uuid4() for _ in range(101)])


def test_bulk_delete_schema_accepts_valid_payload():
    ids = [uuid.uuid4(), uuid.uuid4()]
    body = ThreadBulkDeleteIn(thread_ids=ids)
    assert body.thread_ids == ids
