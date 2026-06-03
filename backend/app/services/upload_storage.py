"""Локальное хранение бинарников вложений (фото для vision)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _root() -> Path:
    root = Path(get_settings().upload_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload_bytes(user_id: UUID, file_id: UUID, data: bytes, ext: str) -> str:
    rel = f"{user_id}/{file_id}.{ext}"
    path = _root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def load_upload_bytes(storage_key: str | None) -> bytes | None:
    if not storage_key:
        return None
    path = _root() / storage_key
    if not path.is_file():
        logger.warning("upload file missing on disk: %s", storage_key)
        return None
    return path.read_bytes()


def delete_upload_file(storage_key: str | None) -> None:
    if not storage_key:
        return
    path = _root() / storage_key
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("failed to delete upload %s", storage_key)
    parent = path.parent
    if parent.is_dir() and not any(parent.iterdir()):
        try:
            parent.rmdir()
        except OSError:
            pass


def mime_for_ext(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"
