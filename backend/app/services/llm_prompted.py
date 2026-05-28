"""Общий доступ к промптам по namespace провайдера (yandex_gpt_*, anthropic_claude_*)."""

from __future__ import annotations

from app.services.prompts.store import PromptStore


class PromptedLLMMixin:
    prompt_namespace: str = "yandex_gpt"
    prompts: PromptStore | None = None

    async def get_prompt(self, suffix: str, default: str) -> str:
        key = f"{self.prompt_namespace}_{suffix}"
        if self.prompts:
            raw = await self.prompts.get(key, default=default)
        else:
            raw = default
        text = str(raw or "").strip()
        return text if text else default.strip()
