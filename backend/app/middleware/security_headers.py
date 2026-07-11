"""Global HTTP security headers for API responses."""

from __future__ import annotations

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # X-Frame-Options убран — управляется через CSP frame-ancestors (выше)
    # "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    # CSP: разрешаем только свои скрипты, стили, данные с нашего API
    # unsafe-inline нужен для vite-inject стилей; nonce-based CSP — следующий шаг
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://mc.yandex.ru; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https: blob:; "
        "media-src 'self' blob: https:; "
        # connect-src включает любые источники откуда фронт делает fetch
        # (api.glosix.ru, mc.yandex.ru, а также MAX WebApp SDK endpoints)
        "connect-src 'self' https: wss:; "
        # frame-ancestors: разрешаем любой источник т.к. MAX Desktop (QtWebEngine)
        # может иметь frame parent типа app:// / file:// не покрытый явным списком
        "frame-ancestors *; "
        "object-src 'none'; "
        "base-uri 'self';"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
