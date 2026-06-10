import asyncio

from starlette.requests import Request
from starlette.responses import Response

from app.middleware.security_headers import SecurityHeadersMiddleware


async def _call_next(_request: Request) -> Response:
    return Response(content="ok")


def test_security_headers_middleware():
    middleware = SecurityHeadersMiddleware(app=None)

    async def run() -> Response:
        scope = {"type": "http", "method": "GET", "path": "/api/health", "headers": []}
        request = Request(scope)
        return await middleware.dispatch(request, _call_next)

    response = asyncio.run(run())
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
