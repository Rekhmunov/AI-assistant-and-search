"""Security headers for private user data API routes."""

from __future__ import annotations

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

NOINDEX_VALUE = "noindex, nofollow, noarchive"
_PRIVATE_PREFIXES = (
    "/api/auth",
    "/api/search",
    "/api/threads",
    "/api/users",
    "/api/messages",
    "/api/files",
    "/api/voice",
    "/api/support",
    "/api/payments",
    "/api/feedback",
)


def is_private_api_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PRIVATE_PREFIXES)


class PrivateApiHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if not is_private_api_path(request.url.path):
            return response
        response.headers.setdefault("X-Robots-Tag", NOINDEX_VALUE)
        response.headers.setdefault("Cache-Control", "private, no-store")
        return response
