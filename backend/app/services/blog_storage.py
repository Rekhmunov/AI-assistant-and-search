"""Disk storage for blog images (WebP, long-lived)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _root() -> Path:
    root = Path(get_settings().upload_storage_dir) / "blog"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_blog_image(media_id: UUID, data: bytes) -> str:
    rel = f"blog/{media_id}.webp"
    path = Path(get_settings().upload_storage_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def load_blog_image(storage_key: str) -> bytes | None:
    path = Path(get_settings().upload_storage_dir) / storage_key
    if not path.is_file():
        logger.warning("blog image missing: %s", storage_key)
        return None
    return path.read_bytes()


def delete_blog_image(storage_key: str) -> None:
    path = Path(get_settings().upload_storage_dir) / storage_key
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("failed to delete blog image %s", storage_key)
