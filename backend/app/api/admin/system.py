"""Статус админки и БД для диагностики деплоя."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission

router = APIRouter(prefix="/system", tags=["admin-system"])

FEATURES_VERSION = "thread_debug_v1"


@router.get("/status")
async def system_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("users:read")),
):
    debug_column = False
    deleted_at_column = False
    try:
        await db.execute(text("SELECT debug_trace FROM messages LIMIT 0"))
        debug_column = True
    except ProgrammingError:
        pass

    try:
        await db.execute(text("SELECT deleted_at FROM threads LIMIT 0"))
        deleted_at_column = True
    except ProgrammingError:
        pass

    return {
        "features_version": FEATURES_VERSION,
        "messages_debug_trace_column": debug_column,
        "threads_soft_delete_column": deleted_at_column,
        "thread_debug_api": True,
        "hint": None
        if debug_column
        else "Выполните: docker compose exec backend alembic upgrade head",
    }
