"""Refresh-token cookie attributes (SameSite must match how the browser calls /api)."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from app.core.config import Settings, get_settings


def _normalize_host(host: str | None) -> str:
    if not host:
        return ""
    h = host.lower().strip()
    if h.startswith("www."):
        return h[4:]
    return h


def is_cross_site_cookie_context(request: Request | None, settings: Settings | None = None) -> bool:
    """
    True when the browser Origin host differs from the API Host (e.g. glosix.ru → api.glosix.ru).
    Same-origin proxy (glosix.ru/api on one host) → False → prefer SameSite=Lax (reliable on reload).
    """
    settings = settings or get_settings()
    if settings.debug:
        return True
    if request is None:
        return False
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return False
    origin_host = urlparse(origin).hostname
    req_host = request.url.hostname
    if not origin_host or not req_host:
        return False
    return _normalize_host(origin_host) != _normalize_host(req_host)


def refresh_cookie_kwargs(
    value: str,
    *,
    settings: Settings | None = None,
    request: Request | None = None,
    max_age: int | None = None,
) -> dict:
    settings = settings or get_settings()
    cross_site = is_cross_site_cookie_context(request, settings)
    secure = not settings.debug
    kwargs: dict = {
        "key": "refresh_token",
        "value": value,
        "httponly": True,
        "secure": secure,
        "samesite": "none" if cross_site and secure else "lax",
        "path": "/",
        "max_age": max_age if max_age is not None else settings.refresh_token_expire_days * 86400,
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def refresh_cookie_delete_kwargs(
    settings: Settings | None = None,
    request: Request | None = None,
) -> dict:
    settings = settings or get_settings()
    cross_site = is_cross_site_cookie_context(request, settings)
    secure = not settings.debug
    kwargs: dict = {
        "key": "refresh_token",
        "path": "/",
        "httponly": True,
        "secure": secure,
        "samesite": "none" if cross_site and secure else "lax",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs
