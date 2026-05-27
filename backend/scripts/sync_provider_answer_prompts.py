#!/usr/bin/env python3
"""Синхронизировать answer-промпты провайдера в app_settings (deepseek | anthropic_claude)."""

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
from app.services.prompts.provider_answer_defaults import (
    SUPPORTED_SYNC_PROVIDERS,
    answer_prompts_for_provider,
)


async def sync_provider_answer_prompts(provider_id: str, *, apply: bool) -> None:
    prompts = answer_prompts_for_provider(provider_id)
    settings = get_settings()
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    async with async_session_factory() as db:
        for prompt_id, new_val in prompts.items():
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
            print(f"\nГотово. Answer-промпты {provider_id} в БД и Redis обновлены.")
        else:
            print("\nDry-run. Добавьте --apply для записи.")
    await redis_client.aclose()


async def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--apply"]
    apply = "--apply" in sys.argv
    if not args or args[0] not in SUPPORTED_SYNC_PROVIDERS:
        print(f"Usage: python scripts/sync_provider_answer_prompts.py <{'|'.join(sorted(SUPPORTED_SYNC_PROVIDERS))}> [--apply]")
        sys.exit(1)
    await sync_provider_answer_prompts(args[0], apply=apply)


if __name__ == "__main__":
    asyncio.run(main())
