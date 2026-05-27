#!/usr/bin/env python3
"""Синхронизировать answer-промпты DeepSeek (обёртка над sync_provider_answer_prompts)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "sync_provider_answer_prompts",
    Path(__file__).resolve().parent / "sync_provider_answer_prompts.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


async def _run() -> None:
    apply = "--apply" in sys.argv
    await _mod.sync_provider_answer_prompts("deepseek", apply=apply)


if __name__ == "__main__":
    asyncio.run(_run())
