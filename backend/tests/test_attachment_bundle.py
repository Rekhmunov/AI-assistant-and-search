import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.attachment_bundle import (
    MIN_OCR_CHARS_FOR_TEXT_ONLY,
    resolve_attachment_bundle,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        class S:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        return S(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _FakeResult(self._rows)


def test_bundle_vision_when_ocr_empty():
    uid = uuid.uuid4()
    fid = uuid.uuid4()
    user = User(id=uid, plan="free")
    row = UploadedFile(
        id=fid,
        user_id=uid,
        filename="plant.jpg",
        media_kind="image",
        storage_key=f"{uid}/{fid}.jpg",
        extracted_text="",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    import app.services.attachment_bundle as mod

    orig = mod.load_upload_bytes
    mod.load_upload_bytes = lambda _k: b"\xff\xd8\xff\xe0" + b"\x00" * 100
    try:
        bundle = asyncio.run(
            resolve_attachment_bundle(_FakeDb([row]), user, "Что за растение?", [fid])
        )
    finally:
        mod.load_upload_bytes = orig

    assert bundle.needs_vision is True
    assert len(bundle.vision_images) == 1
    assert "растение" in bundle.llm_query


def test_bundle_text_when_ocr_rich():
    uid = uuid.uuid4()
    fid = uuid.uuid4()
    user = User(id=uid, plan="free")
    ocr = "x" * (MIN_OCR_CHARS_FOR_TEXT_ONLY + 10)
    row = UploadedFile(
        id=fid,
        user_id=uid,
        filename="scan.jpg",
        media_kind="image",
        storage_key=f"{uid}/{fid}.jpg",
        extracted_text=ocr,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    bundle = asyncio.run(
        resolve_attachment_bundle(_FakeDb([row]), user, "Сумма?", [fid])
    )
    assert bundle.needs_vision is False
    assert "--- Фото:" in bundle.llm_query
