#!/usr/bin/env python3
"""Синхронизировать deepseek answer-промпты в app_settings с defaults (прод после git pull)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import redis.asyncio as redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.app_setting import AppSetting
from app.services.prompts.deepseek_defaults import DEEPSEEK_ANSWER_PROMPT_IDS


async def main() -> None:
    apply = "--apply" in sys.argv
    settings = get_settings()
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    async with async_session_factory() as db:
        for prompt_id, new_val in DEEPSEEK_ANSWER_PROMPT_IDS.items():
            key = f"prompt_{prompt_id}"
            result = await db.execute(select(AppSetting).where(AppSetting.key == key))
            row = result.scalar_one_or_none()
            marker = "ЗАМЕНИТЬ" if (not row or row.value != new_val) else "OK"
            print(f"[{marker}] {key}")
            if apply and (not row or row.value != new_val):
                if row:
                    row.value = new_val
                else:
                    db.add(AppSetting(key=key, value=new_val))
                await redis_client.delete(f"setting:{key}")
        if apply:
            await db.commit()
            print("\nГотово. Промпты DeepSeek в БД и Redis обновлены.")
        else:
            print("\nDry-run. Для записи: python scripts/sync_deepseek_prompts.py --apply")
    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
