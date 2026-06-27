"""Проверка и MIME для бинарников изображений."""

from __future__ import annotations

_JPEG_SIG = b"\xff\xd8\xff"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
# WebP: "RIFF????WEBP" where ???? is 4 file-size bytes
_RIFF_SIG = b"RIFF"
_WEBP_SIG = b"WEBP"


def detect_image_mime(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == _JPEG_SIG:
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == _PNG_SIG:
        return "image/png"
    if len(data) >= 12 and data[:4] == _RIFF_SIG and data[8:12] == _WEBP_SIG:
        return "image/webp"
    return None


def is_valid_image_bytes(data: bytes, *, min_size: int = 128) -> bool:
    return len(data) >= min_size and detect_image_mime(data) is not None
