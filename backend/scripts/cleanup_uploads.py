#!/usr/bin/env python3
"""Удалить просроченные uploaded_files. Запуск: python scripts/cleanup_uploads.py"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.upload_lifecycle import cleanup_expired_uploads
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _run() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            deleted = await cleanup_expired_uploads(db)
            await db.commit()
            return deleted
    finally:
        await engine.dispose()


def main() -> None:
    n = asyncio.run(_run())
    print(f"Deleted {n} expired upload(s)")


if __name__ == "__main__":
    main()
