"""Подписанные ссылки на скачивание файла без Bearer (share fallback)."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import Settings, get_settings


def _secret(settings: Settings) -> bytes:
    raw = (settings.jwt_secret or "change-me").encode()
    return raw


def share_token_ttl_seconds_for_expires_at(
    expires_at: datetime | None,
    *,
    min_seconds: int = 60,
    fallback_seconds: int = 3600,
) -> int:
    """TTL share-ссылки = оставшееся время жизни файла (не полный срок заново)."""
    if expires_at is None:
        return fallback_seconds
    now = datetime.now(timezone.utc)
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    remaining = int((exp - now).total_seconds())
    return max(min_seconds, remaining)


def create_file_share_token(file_id: UUID, *, ttl_seconds: int, settings: Settings | None = None) -> tuple[str, int]:
    settings = settings or get_settings()
    exp = int(time.time()) + max(60, ttl_seconds)
    payload = f"{file_id}:{exp}"
    sig = hmac.new(_secret(settings), payload.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}", exp


def verify_file_share_token(file_id: UUID, token: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not token or "." not in token:
        return False
    exp_s, sig = token.split(".", 1)
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{file_id}:{exp}"
    expected = hmac.new(_secret(settings), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
