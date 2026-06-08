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
                "Галерея фото — через Yandex Image Search (нужны YANDEX_* ключи). "
                "Lite и Pro в Glosix сейчас оба идут в sonar (sonar-pro отключён)."
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
VALID_FREE_LLM_IDS = frozenset({"deepseek", "gigachat"})
VALID_SEARCH_IDS = frozenset({"yandex_search"})
VALID_VISION_IDS = frozenset({"alice_vlm", "anthropic_claude", "gigachat"})
VALID_IMAGE_GEN_IDS = frozenset({"gigachat"})
DEFAULT_IMAGE_GEN_PROVIDER = "gigachat"


def list_image_gen_providers(settings: Settings) -> list[ProviderInfo]:
    giga_ok = settings.gigachat_configured
    return [
        ProviderInfo(
            id="gigachat",
            label="GigaChat (text2image)",
            kind="image_gen",
            configured=giga_ok,
            hint=None if giga_ok else "Нужен GIGACHAT_CREDENTIALS в .env",
        ),
    ]


def list_free_llm_providers(settings: Settings) -> list[ProviderInfo]:
    """Провайдеры для Free-аккаунтов: только DeepSeek и GigaChat (lite в коде)."""
    all_llm = {p.id: p for p in list_llm_providers(settings)}
    out: list[ProviderInfo] = []
    for pid in ("deepseek", "gigachat"):
        p = all_llm.get(pid)
        if p:
            out.append(
                ProviderInfo(
                    id=p.id,
                    label=p.label,
                    kind="llm",
                    configured=p.configured,
                    hint="Free: только lite-модель и лимит free_searches_per_day",
                )
            )
    return out


def list_vision_providers(settings: Settings) -> list[ProviderInfo]:
    alice_ok = settings.yandex_configured
    claude_ok = settings.anthropic_configured
    giga_ok = settings.gigachat_configured
    return [
        ProviderInfo(
            id="alice_vlm",
            label="Alice AI VLM",
            kind="vision",
            configured=alice_ok,
            hint=None if alice_ok else "Нужны YANDEX_FOLDER_ID и YANDEX_API_KEY в .env",
        ),
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
