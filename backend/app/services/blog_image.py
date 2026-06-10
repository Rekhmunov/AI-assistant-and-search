"""Compress blog images to WebP for economical storage."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

ALLOWED_UPLOAD_MIME = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}
)

COVER_MAX_EDGE = 1280
INLINE_MAX_EDGE = 1600
WEBP_QUALITY = 82


@dataclass
class ProcessedBlogImage:
    data: bytes
    width: int
    height: int
    mime_type: str = "image/webp"


def _open_image(data: bytes) -> Image.Image:
    if data[:12].lower().find(b"ftypheic") >= 0 or data[:12].lower().find(b"ftypheif") >= 0:
        from app.services.file_parser import _register_heif_opener

        _register_heif_opener()
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def process_blog_image(data: bytes, *, purpose: str = "inline") -> ProcessedBlogImage:
    max_edge = COVER_MAX_EDGE if purpose == "cover" else INLINE_MAX_EDGE
    img = _open_image(data)
    w, h = img.size
    scale = min(1.0, max_edge / max(w, h))
    if scale < 1.0:
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        w, h = new_w, new_h

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    out = buf.getvalue()
    return ProcessedBlogImage(data=out, width=w, height=h)
