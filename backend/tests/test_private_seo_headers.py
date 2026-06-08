import asyncio

from starlette.requests import Request
from starlette.responses import Response

from app.middleware.private_api_headers import (
    NOINDEX_VALUE,
    PrivateApiHeadersMiddleware,
    is_private_api_path,
)


def test_is_private_api_path():
    assert is_private_api_path("/api/search")
    assert is_private_api_path("/api/threads/abc")
    assert is_private_api_path("/api/files/uuid/shared")
    assert not is_private_api_path("/api/health")
    assert not is_private_api_path("/health")


async def _call_next(_request: Request) -> Response:
    return Response(content="ok")


def test_private_api_headers_middleware():
    middleware = PrivateApiHeadersMiddleware(app=None)

    async def run(path: str) -> Response:
        scope = {"type": "http", "method": "GET", "path": path, "headers": []}
        request = Request(scope)
        return await middleware.dispatch(request, _call_next)

    private = asyncio.run(run("/api/threads"))
    assert private.headers.get("X-Robots-Tag") == NOINDEX_VALUE
    assert private.headers.get("Cache-Control") == "private, no-store"

    public = asyncio.run(run("/api/health"))
    assert "X-Robots-Tag" not in public.headers
