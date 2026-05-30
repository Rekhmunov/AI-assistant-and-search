"""Проверка наличия колонки messages.images (миграция 011)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

_images_column_ok: bool | None = None


async def messages_have_images_column(db: AsyncSession) -> bool:
    global _images_column_ok
    if _images_column_ok is not None:
        return _images_column_ok
    try:
        await db.execute(text("SELECT images FROM messages LIMIT 0"))
        _images_column_ok = True
    except ProgrammingError:
        await db.rollback()
        _images_column_ok = False
    return _images_column_ok
