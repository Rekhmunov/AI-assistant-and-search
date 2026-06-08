from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis, require_admin_or_api_key
from app.core.config import get_settings
from app.services.anthropic_probe import probe_anthropic
from app.services.deepseek_probe import probe_deepseek
from app.services.gigachat_probe import probe_gigachat
from app.services.perplexity_probe import probe_perplexity
from app.services.llm_runtime import fetch_llm_runtime_status
from app.services.query_router import POLICY_VERSION
from app.services.file_format import UNSUPPORTED_FORMAT_MESSAGE
from app.services.yandex_probe import probe_yandex

router = APIRouter(tags=["health"])

UPLOAD_API_VERSION = 3


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
    try:
        from app.services import facts  # noqa: F401

        fact_pipeline = True
    except ImportError:
        fact_pipeline = False
    page_cache_on = get_settings().page_cache_enabled
    s = get_settings()
    return {
        "policy_v6_context": POLICY_VERSION.startswith("v6"),
        "fact_pipeline": fact_pipeline,
        "page_cache": page_cache_on,
        "query_url_index": s.query_url_index_enabled,
        "page_fetch_parallel": s.page_fetch_max_concurrent > 1,
        "page_fetch_max_pages": s.page_fetch_max_pages,
        "page_fetch_skip_rich_snippet_chars": s.page_fetch_skip_rich_snippet_chars,
        "search_parallel_extra": s.search_parallel_extra_queries,
        "follow_ups_deferred": s.follow_ups_deferred,
        "follow_ups_post_done_timeout_sec": s.follow_ups_post_done_timeout_sec,
        "currency_cbr": currency_cbr,
        "page_fetch": page_fetch,
    }


@router.get("/health/query-url-index")
async def api_health_query_url_index(
    db: Annotated[AsyncSession, Depends(get_db)],
    _auth: Annotated[None, Depends(require_admin_or_api_key)],
):
    """Статистика памяти query → URL (Postgres)."""
    from app.services.query_url_memory import index_stats

    return await index_stats(db)


@router.get("/health/page-cache")
async def api_health_page_cache(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Статистика Redis page_cache (приблизительно)."""
    from app.core.config import get_settings
    from app.services.page_cache import cache_stats_sample

    settings = get_settings()
    stats = await cache_stats_sample()
    return {
        "enabled": settings.page_cache_enabled,
        **stats,
    }


@router.get("/health")
async def api_health(db: Annotated[AsyncSession, Depends(get_db)]):
    """Проверка API и БД (для curl https://glosix.ru/api/health)."""
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

    msg_cols = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'messages'
              AND column_name = 'images'
            """
        )
    )
    message_images_column = bool(msg_cols.fetchall())

    redis_ok = True
    try:
        redis = await get_redis()
        await redis.ping()
    except Exception:
        redis_ok = False

    settings = get_settings()
    llm_runtime = None
    if redis_ok:
        try:
            redis = await get_redis()
            llm_runtime = await fetch_llm_runtime_status(db, redis, settings)
        except Exception:
            pass
    status = "ok" if not missing and not missing_tables and redis_ok and message_images_column else "degraded"
    return {
        "status": status,
        "redis": redis_ok,
        "yandex_configured": settings.yandex_configured,
        "anthropic_configured": settings.anthropic_configured,
        "deepseek_configured": settings.deepseek_configured,
        "gigachat_configured": settings.gigachat_configured,
        "perplexity_configured": settings.perplexity_configured,
        "llm_runtime": llm_runtime,
        "yandex_models": {
            "lite": settings.yandex_gpt_lite_model,
            "pro": settings.yandex_gpt_pro_model,
        },
        "anthropic_models": {
            "lite": settings.anthropic_model_lite,
            "pro": settings.anthropic_model_pro,
        },
        "deepseek_models": {
            "lite": settings.deepseek_model_lite,
            "pro": settings.deepseek_model_pro,
        },
        "gigachat_models": {
            "lite": settings.gigachat_model_lite,
            "pro": settings.gigachat_model_pro,
        },
        "perplexity_models": {
            "lite": settings.perplexity_model_lite,
            "pro": settings.perplexity_model_pro,
        },
        "db_columns": {c: c in cols for c in sorted(required)},
        "message_images_column": message_images_column,
        "missing_migrations": missing,
        "missing_tables": missing_tables,
        "hint": (
            "На сервере: docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
            if missing or missing_tables or not message_images_column
            else None
        ),
        "yandex_hint": (
            None
            if settings.yandex_configured
            else "Добавьте YANDEX_FOLDER_ID и YANDEX_API_KEY в .env — см. docs/YANDEX_SETUP.md"
        ),
        "upload_api_version": UPLOAD_API_VERSION,
        "upload_images": True,
        "upload_formats_hint": UNSUPPORTED_FORMAT_MESSAGE,
        "features": _build_features(),
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
async def api_health_yandex(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Проверка Search API и YandexGPT Lite/Pro (может занять до ~30 с)."""
    return await probe_yandex()


@router.get("/health/anthropic")
async def api_health_anthropic(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Тест Anthropic с ANTHROPIC_API_KEY из .env (появится в Usage консоли)."""
    return await probe_anthropic()


@router.get("/health/deepseek")
async def api_health_deepseek(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Тест DeepSeek с DEEPSEEK_API_KEY из .env (lite + pro)."""
    return await probe_deepseek()


@router.get("/health/gigachat")
async def api_health_gigachat(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Тест GigaChat с GIGACHAT_CREDENTIALS из .env (OAuth, lite + pro)."""
    return await probe_gigachat()


@router.get("/health/perplexity")
async def api_health_perplexity(_auth: Annotated[None, Depends(require_admin_or_api_key)]):
    """Тест Perplexity Sonar с PERPLEXITY_API_KEY из .env."""
    return await probe_perplexity()
