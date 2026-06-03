"""Безопасный Content-Disposition для имён с кириллицей (RFC 5987)."""

from __future__ import annotations

from urllib.parse import quote


def attachment_content_disposition(filename: str) -> str:
    """attachment с filename* (UTF-8), чтобы не ловить latin-1 в Starlette."""
    ascii_fallback = "".join(
        c if ord(c) < 128 and c not in ('"', "\\", "\r", "\n") else "_"
        for c in filename
    ).strip() or "download"
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'
