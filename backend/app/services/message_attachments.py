"""Сериализация вложений пользователя для UI и API."""

from __future__ import annotations

from uuid import UUID

from app.core.config import Settings, get_settings
from app.models.uploaded_file import UploadedFile
from app.schemas.thread import MessageAttachmentOut
from app.services.attachment_bundle import _is_image_row
from app.services.file_share_token import create_file_share_token, share_token_ttl_seconds_for_expires_at
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


def message_attachments_out(
    raw_list: list[dict] | None,
    *,
    settings: Settings | None = None,
    files_by_id: dict[UUID, UploadedFile] | None = None,
) -> list[MessageAttachmentOut] | None:
    if not raw_list:
        return None
    settings = settings or get_settings()
    files_by_id = files_by_id or {}
    out: list[MessageAttachmentOut] = []
    for item in raw_list:
        data = dict(item)
        kind = str(data.get("kind") or "document")
        if kind == "markdown_document":
            out.append(MessageAttachmentOut(**data))
            continue
        file_id_raw = data.get("id")
        if kind == "document" and file_id_raw:
            try:
                file_id = UUID(str(file_id_raw))
            except ValueError:
                out.append(MessageAttachmentOut(**data))
                continue

            file_row = files_by_id.get(file_id)
            if file_row and file_row.expires_at:
                data["expires_at"] = file_row.expires_at

            ttl_seconds = share_token_ttl_seconds_for_expires_at(
                file_row.expires_at if file_row else None,
                fallback_seconds=max(3600, int(data.get("ttl_hours") or settings.generated_doc_ttl_hours) * 3600),
            )
            share_token, _ = create_file_share_token(
                file_id,
                ttl_seconds=ttl_seconds,
                settings=settings,
            )
            data["share_url"] = f"/api/files/{file_id}/shared?token={share_token}"
            if not data.get("url"):
                data["url"] = public_file_content_url(file_id, settings)
        out.append(MessageAttachmentOut(**data))
    return out
