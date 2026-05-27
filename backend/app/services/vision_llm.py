"""Vision-ответы через Claude (мультимодальный API)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.config import Settings, get_settings
from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.attachment_bundle import VisionImage
from app.services.prompts.store import PromptStore
from app.services.yandex_errors import YandexServiceError


class VisionNotSupportedError(Exception):
    """Нет настроенного провайдера с поддержкой изображений."""


async def stream_vision_answer(
    query: str,
    vision_images: list[VisionImage],
    history: list[tuple[str, str]],
    *,
    model: str = "pro",
    prior_sources_block: str = "",
    settings: Settings | None = None,
    prompt_store: PromptStore | None = None,
) -> AsyncIterator[str]:
    settings = settings or get_settings()
    if not settings.anthropic_configured:
        raise VisionNotSupportedError(
            "Анализ фото без текста доступен при настроенном ANTHROPIC_API_KEY (Claude). "
            "Либо загрузите документ с текстом (PDF, Word)."
        )

    claude = AnthropicClaudeProvider(settings, prompt_store=prompt_store)
    answer_model = "pro" if model == "pro" else "lite"
    try:
        async for chunk in claude.stream_answer_vision(
            query,
            vision_images,
            history,
            model=answer_model,  # type: ignore[arg-type]
            prior_sources_block=prior_sources_block,
        ):
            yield chunk
    except YandexServiceError:
        raise
