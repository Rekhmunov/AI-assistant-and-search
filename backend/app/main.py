from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import get_settings
from app.core.database import async_session_factory
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
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Guest-Session"],
    )

    app.include_router(api_router)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        import logging

        logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def api_root():
        return {
            "service": settings.app_name,
            "status": "ok",
            "health": "/health",
            "api": "/api",
        }

    return app


app = create_app()
