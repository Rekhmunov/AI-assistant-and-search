"""Проверка URL картинок до отправки клиенту — без битых превью."""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_MIN_BYTES = 400
_MIN_WIDTH = 120
_MIN_HEIGHT = 120


def _magic_is_image(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


async def validate_image_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float,
) -> bool:
    if not url.startswith("https://"):
        return False
    try:
        async with client.stream("GET", url, follow_redirects=True, timeout=timeout) as resp:
            if resp.status_code != 200:
                return False
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                return False
            buf = bytearray()
            async for chunk in resp.aiter_bytes(4096):
                buf.extend(chunk)
                if len(buf) >= _MIN_BYTES:
                    break
            if len(buf) < _MIN_BYTES:
                return False
            if not _magic_is_image(bytes(buf)):
                return False
            return True
    except Exception:
        logger.debug("Image URL validation failed: %s", url[:120], exc_info=True)
        return False


async def filter_valid_image_urls(
    candidates: list[tuple[str, str, str, int | None, int | None]],
    *,
    limit: int,
    timeout: float,
    max_concurrent: int = 4,
) -> list[tuple[str, str, str, int | None, int | None]]:
    """
    candidates: (url, title, page_url, width, height)
    Возвращает только URL, которые реально отдают изображение.
    """
    if not candidates or limit <= 0:
        return []

    sem = asyncio.Semaphore(max_concurrent)
    valid: list[tuple[str, str, str, int | None, int | None]] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(
        headers={"User-Agent": "Glosix/1.0 (+https://app.glosix.ru)"},
        follow_redirects=True,
    ) as client:

        async def check(item: tuple[str, str, str, int | None, int | None]) -> None:
            if len(valid) >= limit:
                return
            url, title, page_url, width, height = item
            key = url.lower().split("#", 1)[0]
            if key in seen_urls:
                return
            if width is not None and width < _MIN_WIDTH:
                return
            if height is not None and height < _MIN_HEIGHT:
                return
            async with sem:
                if len(valid) >= limit:
                    return
                ok = await validate_image_url(client, url, timeout=timeout)
            if ok:
                seen_urls.add(key)
                valid.append(item)

        await asyncio.gather(*(check(c) for c in candidates))
    return valid[:limit]
