from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.api.blog_pages import router as blog_pages_router
from app.api.site import router as site_router
from app.core.config import get_settings
from app.middleware.private_api_headers import PrivateApiHeadersMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.core.database import async_session_factory
from app.core.production_guards import assert_production_security
from app.services.admin_bootstrap import ensure_bootstrap_admin
from app.services.app_settings import sync_settings_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with async_session_factory() as db:
            await ensure_bootstrap_admin(db)
            from app.api.deps import get_redis

            redis_client = await get_redis()
            await sync_settings_cache(db, redis_client)
            await db.commit()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Startup bootstrap failed")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    assert_production_security(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Guest-Session"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrivateApiHeadersMiddleware)

    @app.middleware("http")
    async def log_voice_requests(request: Request, call_next):
        import logging

        path = request.url.path
        if path.startswith("/api/voice"):
            logging.getLogger("app.voice").info(
                "voice HTTP %s %s cl=%s origin=%s referer=%s",
                request.method,
                path,
                request.headers.get("content-length"),
                request.headers.get("origin"),
                (request.headers.get("referer") or "")[:120],
            )
        return await call_next(request)

    app.include_router(api_router)
    app.include_router(blog_pages_router)
    app.include_router(site_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception(request: Request, exc: RequestValidationError):
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        from starlette.exceptions import HTTPException as StarletteHTTPException

        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)

        if isinstance(exc, StarletteHTTPException):
            detail = exc.detail
            if not isinstance(detail, str):
                detail = str(detail)
            return JSONResponse(status_code=exc.status_code, content={"detail": detail})

        import logging

        logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
