"""Сжатие изображений через Pillow."""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

_IMAGE_MIME_TYPES = frozenset({
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/heic", "image/heif",
})

# (quality, max_side_px or None)
_LEVEL_PARAMS: dict[str, tuple[int, int | None]] = {
    "light":  (85, None),   # лёгкое — только quality
    "medium": (72, 1920),   # среднее — quality + ограничение стороны
    "strong": (55, 1280),   # сильное — максимальная компрессия
    "web":    (65, 1280),   # для сайта/соцсетей
}

_LEVEL_LABELS = {
    "light":  "лёгкое",
    "medium": "среднее",
    "strong": "максимальное",
    "web":    "для веба",
}


def detect_compress_level(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ("максимальн", "сильн", "strong", "мал", "минимальн")):
        return "strong"
    if any(w in t for w in ("лёгк", "легк", "чуть", "немного", "слегка", "light")):
        return "light"
    if any(w in t for w in ("сайт", "web", "соцсет", "инстаграм", "телеграм", "vk", "вк")):
        return "web"
    return "medium"


def compress_image_bytes(data: bytes, level: str = "medium") -> tuple[bytes, str]:
    """
    Сжимает изображение.
    Возвращает (bytes, mime_type) — всегда JPEG на выходе.
    """
    from PIL import Image

    quality, max_side = _LEVEL_PARAMS.get(level, _LEVEL_PARAMS["medium"])

    try:
        with Image.open(io.BytesIO(data)) as img:
            # HEIC/HEIF обрабатывается pillow-heif автоматически через Image.open
            img = img.convert("RGB")

            if max_side:
                w, h = img.size
                if w > max_side or h > max_side:
                    img.thumbnail((max_side, max_side), Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("compress_image_bytes failed: %s", exc)
        raise


def is_image_mime(mime: str) -> bool:
    return (mime or "").lower() in _IMAGE_MIME_TYPES


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} МБ"
    return f"{size_bytes / 1024:.0f} КБ"
