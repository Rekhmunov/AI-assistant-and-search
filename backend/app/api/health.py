from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.config import get_settings
from app.services.query_router import POLICY_VERSION
from app.services.yandex_probe import probe_yandex

router = APIRouter(tags=["health"])


def _build_features() -> dict[str, bool]:
    try:
        from app.services import currency_rates  # noqa: F401

        currency_cbr = True
    except ImportError:
        currency_cbr = False
    try:
        from app.services import source_page_fetch  # noqa: F401

        page_fetch = True
    except ImportError:
        page_fetch = False
    return {
        "policy_v4_persona": POLICY_VERSION.startswith("v4"),
        "currency_cbr": currency_cbr,
        "page_fetch": page_fetch,
    }


@router.get("/health")
async def api_health(db: Annotated[AsyncSession, Depends(get_db)]):
    """Проверка API и БД (для curl https://app.glosix.ru/api/health)."""
    await db.execute(text("SELECT 1"))

    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'users'
              AND column_name IN ('email', 'password_hash', 'guest_key')
            """
        )
    )
    cols = {row[0] for row in result.fetchall()}
    admin_cols = await db.execute(
        text(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('admin_users', 'app_settings', 'broadcasts')
            """
        )
    )
    admin_tables = {row[0] for row in admin_cols.fetchall()}
    required_tables = {"admin_users", "app_settings", "broadcasts"}
    missing_tables = sorted(required_tables - admin_tables)

    required = {"email", "password_hash", "guest_key"}
    missing = sorted(required - cols)

    redis_ok = True
    try:
        redis = await get_redis()
        await redis.ping()
    except Exception:
        redis_ok = False

    settings = get_settings()
    status = "ok" if not missing and not missing_tables and redis_ok else "degraded"
    return {
        "status": status,
        "redis": redis_ok,
        "yandex_configured": settings.yandex_configured,
        "yandex_models": {
            "lite": settings.yandex_gpt_lite_model,
            "pro": settings.yandex_gpt_pro_model,
        },
        "db_columns": {c: c in cols for c in sorted(required)},
        "missing_migrations": missing,
        "missing_tables": missing_tables,
        "hint": (
            "На сервере: docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
            if missing or missing_tables
            else None
        ),
        "yandex_hint": (
            None
            if settings.yandex_configured
            else "Добавьте YANDEX_FOLDER_ID и YANDEX_API_KEY в .env — см. docs/YANDEX_SETUP.md"
        ),
    }


@router.get("/health/version")
async def api_health_version():
    """
    Версия backend для проверки деплоя (curl /api/health/version).
    GIT_COMMIT задаётся при сборке образа или в .env.
    """
    import os

    settings = get_settings()
    return {
        "app": settings.app_name,
        "policy_version": POLICY_VERSION,
        "git_commit": os.environ.get("GIT_COMMIT") or "unknown",
        "features": _build_features(),
    }


@router.get("/health/yandex")
async def api_health_yandex():
    """Проверка Search API и YandexGPT Lite/Pro (может занять до ~30 с)."""
    return await probe_yandex()
