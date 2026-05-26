"""Реестр LLM и поисковых провайдеров (расширяемый список для админки)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    kind: str  # llm | search
    configured: bool
    hint: str | None = None


def list_llm_providers(settings: Settings) -> list[ProviderInfo]:
    yandex_ok = settings.yandex_configured
    claude_ok = settings.anthropic_configured
    deepseek_ok = settings.deepseek_configured
    return [
        ProviderInfo(
            id="yandex_gpt",
            label="Yandex GPT",
            kind="llm",
            configured=yandex_ok,
            hint=None if yandex_ok else "Нужны YANDEX_FOLDER_ID и YANDEX_API_KEY в .env",
        ),
        ProviderInfo(
            id="anthropic_claude",
            label="Claude (Anthropic)",
            kind="llm",
            configured=claude_ok,
            hint=(
                "Тот же пайплайн Glosix: Yandex Search + RAG; меняется только LLM."
                if claude_ok
                else "Нужен ANTHROPIC_API_KEY в .env"
            ),
        ),
        ProviderInfo(
            id="deepseek",
            label="DeepSeek",
            kind="llm",
            configured=deepseek_ok,
            hint=(
                "Тот же пайплайн Glosix: Yandex Search + RAG; меняется только LLM."
                if deepseek_ok
                else "Нужен DEEPSEEK_API_KEY в .env"
            ),
        ),
    ]


def list_search_providers(settings: Settings) -> list[ProviderInfo]:
    yandex_ok = settings.yandex_configured
    return [
        ProviderInfo(
            id="yandex_search",
            label="Yandex Search",
            kind="search",
            configured=yandex_ok,
            hint=None if yandex_ok else "Нужны YANDEX_FOLDER_ID и YANDEX_API_KEY в .env",
        ),
    ]


VALID_LLM_IDS = frozenset({"yandex_gpt", "anthropic_claude", "deepseek"})
VALID_SEARCH_IDS = frozenset({"yandex_search"})
