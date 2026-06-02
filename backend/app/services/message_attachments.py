"""Сериализация вложений пользователя для UI (чипы под сообщением)."""

from __future__ import annotations

from uuid import UUID

from app.core.config import Settings, get_settings
from app.models.uploaded_file import UploadedFile
from app.services.attachment_bundle import _is_image_row
from app.services.image_gen_service import public_file_content_url


def attachments_json_from_files(files: list[UploadedFile]) -> list[dict]:
    settings = get_settings()
    out: list[dict] = []
    for row in files:
        kind = "image" if _is_image_row(row) else "document"
        item: dict = {
            "id": str(row.id),
            "filename": row.filename,
            "kind": kind,
        }
        if kind == "image" and row.storage_key:
            item["url"] = public_file_content_url(row.id, settings)
        out.append(item)
    return out


def attachments_json_from_ids(
    files_by_id: dict[UUID, UploadedFile],
    attachment_ids: list[UUID],
) -> list[dict]:
    ordered = [files_by_id[fid] for fid in attachment_ids if fid in files_by_id]
    return attachments_json_from_files(ordered)
