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
        ProviderInfo(
            id="gigachat",
            label="GigaChat",
            kind="llm",
            configured=settings.gigachat_configured,
            hint=(
                "Yandex Search + RAG; Lite/Pro в коде. Нужен GIGACHAT_CREDENTIALS в .env."
                if settings.gigachat_configured
                else "Нужен GIGACHAT_CREDENTIALS (authorization key из кабинета Сбера)"
            ),
        ),
        ProviderInfo(
            id="perplexity",
            label="Perplexity Sonar",
            kind="llm",
            configured=settings.perplexity_configured,
            hint=(
                "Встроенный веб-поиск Perplexity; Yandex Search и Search Planner не используются. "
                "Lite=sonar, Pro=sonar-pro."
                if settings.perplexity_configured
                else "Нужен PERPLEXITY_API_KEY в .env (docs.perplexity.ai)"
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


VALID_LLM_IDS = frozenset({"yandex_gpt", "anthropic_claude", "deepseek", "gigachat", "perplexity"})
VALID_SEARCH_IDS = frozenset({"yandex_search"})
VALID_VISION_IDS = frozenset({"anthropic_claude", "gigachat"})


def list_vision_providers(settings: Settings) -> list[ProviderInfo]:
    claude_ok = settings.anthropic_configured
    giga_ok = settings.gigachat_configured
    return [
        ProviderInfo(
            id="gigachat",
            label="GigaChat (vision)",
            kind="vision",
            configured=giga_ok,
            hint=None if giga_ok else "Нужен GIGACHAT_CREDENTIALS в .env",
        ),
        ProviderInfo(
            id="anthropic_claude",
            label="Claude (vision)",
            kind="vision",
            configured=claude_ok,
            hint=None if claude_ok else "Нужен ANTHROPIC_API_KEY в .env",
        ),
    ]
