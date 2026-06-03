"""Нормализация вложений сообщений для API (подписанные ссылки на docx)."""

from __future__ import annotations

from uuid import UUID

from app.core.config import Settings, get_settings
from app.schemas.thread import MessageAttachmentOut
from app.services.file_share_token import create_file_share_token
from app.services.image_gen_service import public_file_content_url


def message_attachments_out(
    raw_list: list[dict] | None,
    *,
    settings: Settings | None = None,
) -> list[MessageAttachmentOut] | None:
    if not raw_list:
        return None
    settings = settings or get_settings()
    out: list[MessageAttachmentOut] = []
    for item in raw_list:
        data = dict(item)
        kind = str(data.get("kind") or "document")
        file_id_raw = data.get("id")
        if kind == "document" and file_id_raw:
            try:
                file_id = UUID(str(file_id_raw))
            except ValueError:
                out.append(MessageAttachmentOut(**data))
                continue
            ttl_h = int(data.get("ttl_hours") or settings.generated_doc_ttl_hours)
            share_token, _ = create_file_share_token(
                file_id,
                ttl_seconds=max(3600, ttl_h * 3600),
                settings=settings,
            )
            data["share_url"] = f"/api/files/{file_id}/shared?token={share_token}"
            if not data.get("url"):
                data["url"] = public_file_content_url(file_id, settings)
        out.append(MessageAttachmentOut(**data))
    return out
