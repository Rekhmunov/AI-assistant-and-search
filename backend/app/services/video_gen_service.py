"""Генерация видео через BytePlus ModelArk (Seedance 2.0)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.app_settings import get_setting
from app.services.providers.registry import DEFAULT_VIDEO_GEN_PROVIDER, VALID_VIDEO_GEN_IDS

logger = logging.getLogger(__name__)

_BYTEPLUS_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
_MODEL_IDS = {
    "seedance2": "dreamina-seedance-2-0-260128",
    "seedance2_fast": "dreamina-seedance-2-0-fast-260128",
}

_TIMEOUT_SUBMIT = 30.0
_POLL_INTERVAL_SEC = 5.0
_MAX_POLL_ATTEMPTS = 60  # 5 мин максимум


class VideoGenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class VideoGenerationResult:
    video_url: str
    cover_image_url: str | None
    task_id: str
    duration: int
    resolution: str


async def resolve_video_gen_provider_id(db, redis_client) -> str:
    raw = await get_setting("video_gen_provider", db, redis_client)
    pid = str(raw or DEFAULT_VIDEO_GEN_PROVIDER).strip()
    return pid if pid in VALID_VIDEO_GEN_IDS else DEFAULT_VIDEO_GEN_PROVIDER


async def submit_video_task(
    prompt: str,
    *,
    provider_id: str = "seedance2",
    resolution: str = "720p",
    duration: int = 5,
    ratio: str = "16:9",
    generate_audio: bool = False,
    reference_image_url: str | None = None,
) -> str:
    """
    Отправляет задачу генерации видео в BytePlus ModelArk.
    Возвращает task_id.
    """
    settings = get_settings()
    if not settings.byteplus_configured:
        raise VideoGenerationError("provider_unavailable", "BYTEPLUS_API_KEY не настроен")

    model = _MODEL_IDS.get(provider_id, _MODEL_IDS["seedance2"])

    content: list[dict] = [{"type": "text", "text": prompt}]
    if reference_image_url:
        content.insert(0, {"type": "image_url", "image_url": {"url": reference_image_url}})

    payload: dict = {
        "model": model,
        "content": content,
        "ratio": ratio,
        "resolution": resolution,
        "duration": duration,
        "generate_audio": generate_audio,
    }

    headers = {
        "Authorization": f"Bearer {settings.byteplus_api_key.strip()}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SUBMIT) as client:
            resp = await client.post(
                f"{settings.byteplus_base_url}/contents/generations/tasks",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise VideoGenerationError("network_error", f"BytePlus недоступен: {exc}") from exc

    if resp.status_code == 401:
        raise VideoGenerationError("auth_error", "Неверный BYTEPLUS_API_KEY")
    if resp.status_code == 429:
        raise VideoGenerationError("rate_limit", "Превышен лимит запросов BytePlus")
    if not resp.is_success:
        body = resp.text[:300]
        raise VideoGenerationError("api_error", f"BytePlus API ошибка {resp.status_code}: {body}")

    data = resp.json()
    task_id = data.get("id") or data.get("task_id")
    if not task_id:
        raise VideoGenerationError("empty_response", "BytePlus не вернул task_id")

    logger.info("video_gen: task submitted model=%s task_id=%s", model, task_id)
    return str(task_id)


async def poll_video_task(task_id: str) -> VideoGenerationResult:
    """
    Поллинг статуса задачи до completed/failed.
    Возвращает VideoGenerationResult при успехе.
    """
    settings = get_settings()
    if not settings.byteplus_configured:
        raise VideoGenerationError("provider_unavailable", "BYTEPLUS_API_KEY не настроен")

    headers = {
        "Authorization": f"Bearer {settings.byteplus_api_key.strip()}",
    }

    for attempt in range(_MAX_POLL_ATTEMPTS):
        await asyncio.sleep(_POLL_INTERVAL_SEC)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{settings.byteplus_base_url}/contents/generations/tasks/{task_id}",
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            logger.warning("video_gen poll error (attempt %d): %s", attempt, exc)
            continue

        if not resp.is_success:
            logger.warning("video_gen poll HTTP %s (attempt %d)", resp.status_code, attempt)
            continue

        data = resp.json()
        task_status = str(data.get("status") or "").lower()

        logger.info("video_gen poll attempt=%d task_id=%s status=%s", attempt, task_id, task_status)

        if task_status in ("failed", "cancelled"):
            err = data.get("error") or data.get("message") or "Генерация видео не удалась"
            raise VideoGenerationError("generation_failed", str(err)[:200])

        if task_status == "succeeded":
            # Извлекаем video_url из ответа
            content_list = data.get("content") or []
            video_url = None
            cover_url = None
            for item in content_list:
                if isinstance(item, dict):
                    if item.get("type") == "video":
                        video_url = item.get("video_url") or item.get("url")
                    elif item.get("type") == "image":
                        cover_url = item.get("image_url") or item.get("url")

            # Fallback — прямые поля
            if not video_url:
                video_url = data.get("video_url") or data.get("url")

            if not video_url:
                raise VideoGenerationError("empty_response", "BytePlus не вернул video_url")

            logger.info("video_gen: completed task_id=%s video_url=%s", task_id, video_url[:80])
            return VideoGenerationResult(
                video_url=video_url,
                cover_image_url=cover_url,
                task_id=task_id,
                duration=data.get("duration") or 5,
                resolution=data.get("resolution") or "720p",
            )

    raise VideoGenerationError("timeout", f"Генерация не завершилась за {_MAX_POLL_ATTEMPTS * _POLL_INTERVAL_SEC:.0f} сек")
