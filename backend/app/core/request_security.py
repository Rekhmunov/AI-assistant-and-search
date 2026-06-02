"""Optional request hardening for cookie-authenticated mutations."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def verify_allowed_origin(request: Request) -> None:
    """
  For browser cross-site requests, require Origin to match CORS allowlist.
  Skipped when Origin/Referer absent (non-browser clients, same-origin).
  """
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        referer = (request.headers.get("referer") or "").strip()
        if referer:
            from urllib.parse import urlparse

            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if not origin:
        return

    allowed = get_settings().cors_origin_list
    if origin.rstrip("/") not in {o.rstrip("/") for o in allowed}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed")
