from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    )

    app.include_router(api_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
