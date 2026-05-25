"""Redis-кэш текста страниц: gzip, TTL по типу URL, без мусора."""

import gzip
import hashlib
import logging
from urllib.parse import urlparse

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PREFIX = "pc:v1:"
_MIN_CHARS = 400
_MAX_STORE_CHARS = 48_000
_MAX_COMPRESSED_BYTES = 56 * 1024

_SKIP_URL_PARTS = (
    "/login",
    "/signin",
    "/auth",
    "/cart",
    "/checkout",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "vk.com/video",
)

_SKIP_EXTENSIONS = (".pdf", ".zip", ".exe", ".dmg", ".jpg", ".png", ".gif", ".webp")

_redis_bin: redis.Redis | None = None
_redis_unavailable = False


def _redis_binary() -> redis.Redis | None:
    global _redis_bin, _redis_unavailable
    if _redis_unavailable or not get_settings().page_cache_enabled:
        return None
    if _redis_bin is None:
        try:
            _redis_bin = redis.from_url(get_settings().redis_url, decode_responses=False)
        except Exception:
            logger.warning("Page cache Redis client init failed", exc_info=True)
            _redis_unavailable = True
            return None
    return _redis_bin


def cache_key(url: str) -> str:
    digest = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:40]
    return f"{_PREFIX}{digest}"


def should_cache_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    low = url.lower()
    path = urlparse(low).path
    if any(path.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False
    if any(part in low for part in _SKIP_URL_PARTS):
        return False
    return True


def ttl_seconds(url: str) -> int:
    """TTL: свежие темы короче, справочники дольше."""
    u = url.lower()
    if any(x in u for x in ("pogoda", "gismeteo", "weather", "meteoinfo", "rp5.ru")):
        return 3600
    if "cbr.ru" in u or "banki.ru/currency" in u:
        return 1800
    if any(x in u for x in ("lenta.ru", "/news", "rbc.ru", "tass.com", "interfax")):
        return 6 * 3600
    if any(
        x in u
        for x in (
            "rusprofile",
            "list-org",
            "e-grul",
            "spark-interfax",
            "kommersant",
            "wikipedia.org",
            "yandex.ru/support",
            "cloud.yandex",
        )
    ):
        return 72 * 3600
    return 48 * 3600


async def get_cached_page_text(url: str) -> str | None:
    client = _redis_binary()
    if not client or not should_cache_url(url):
        return None
    try:
        raw = await client.get(cache_key(url))
        if not raw:
            return None
        text = gzip.decompress(raw).decode("utf-8")
        if len(text) < _MIN_CHARS:
            await client.delete(cache_key(url))
            return None
        return text
    except Exception:
        logger.debug("Page cache read failed for %s", url, exc_info=True)
        try:
            await client.delete(cache_key(url))
        except Exception:
            pass
        return None


async def set_cached_page_text(url: str, text: str) -> bool:
    if not should_cache_url(url) or len(text) < _MIN_CHARS:
        return False
    store = text[:_MAX_STORE_CHARS].encode("utf-8")
    try:
        payload = gzip.compress(store, compresslevel=6)
    except Exception:
        return False
    if len(payload) > _MAX_COMPRESSED_BYTES:
        logger.debug("Page cache skip (too large): %s %d bytes", url, len(payload))
        return False
    client = _redis_binary()
    if not client:
        return False
    try:
        await client.set(cache_key(url), payload, ex=ttl_seconds(url))
        return True
    except Exception:
        logger.debug("Page cache write failed for %s", url, exc_info=True)
        return False


async def cache_stats_sample() -> dict[str, int | bool]:
    """Лёгкая статистика для health (SCAN с лимитом)."""
    client = _redis_binary()
    if not client:
        return {"enabled": False, "keys_approx": 0}
    try:
        count = 0
        async for _ in client.scan_iter(match=f"{_PREFIX}*", count=100):
            count += 1
            if count >= 5000:
                break
        return {"enabled": True, "keys_sampled": count, "capped": count >= 5000}
    except Exception:
        return {"enabled": True, "keys_sampled": -1}
