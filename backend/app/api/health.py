from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis

router = APIRouter(tags=["health"])


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

    status = "ok" if not missing and not missing_tables and redis_ok else "degraded"
    return {
        "status": status,
        "redis": redis_ok,
        "db_columns": {c: c in cols for c in sorted(required)},
        "missing_migrations": missing,
        "missing_tables": missing_tables,
        "hint": (
            "На сервере: docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
            if missing or missing_tables
            else None
        ),
    }
