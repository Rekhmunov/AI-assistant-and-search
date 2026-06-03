"""Optional request hardening for cookie-authenticated mutations."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from urllib.parse import urlparse

from app.core.config import get_settings


def _origin_matches_allowed(origin: str, allowed: set[str]) -> bool:
    normalized = origin.rstrip("/")
    if normalized in allowed:
        return True
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if host.startswith("www."):
        alt = f"{parsed.scheme}://{host[4:]}"
        return alt.rstrip("/") in allowed
    alt = f"{parsed.scheme}://www.{host}"
    return alt.rstrip("/") in allowed


def verify_allowed_origin(request: Request) -> None:
    """
  For browser cross-site requests, require Origin to match CORS allowlist.
  Skipped when Origin/Referer absent (non-browser clients, same-origin).
  """
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        referer = (request.headers.get("referer") or "").strip()
        if referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if not origin:
        return

    allowed_set = {o.rstrip("/") for o in get_settings().cors_origin_list}
    if not _origin_matches_allowed(origin, allowed_set):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Запрос с неразрешённого адреса сайта. Откройте glosix.ru или добавьте домен в CORS_ORIGINS.",
        )
