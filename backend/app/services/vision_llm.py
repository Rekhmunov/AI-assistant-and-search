"""Обратная совместимость: делегирует в vision_service."""

from app.services.vision_service import (
    VisionNotSupportedError,
    stream_vision_answer,
    summarize_vision_for_search,
)

__all__ = [
    "VisionNotSupportedError",
    "stream_vision_answer",
    "summarize_vision_for_search",
]
