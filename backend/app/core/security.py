import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings, get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_max_init_data(init_data: str, bot_token: str) -> bool:
    """Validate MAX WebApp initData per https://dev.max.ru/docs/webapps/validation"""
    if not init_data or not bot_token:
        return False

    pairs: list[list[str]] = [part.split("=", 1) for part in init_data.split("&") if "=" in part]
    hash_entries = [p for p in pairs if p[0] == "hash"]
    if len(hash_entries) != 1:
        return False

    original_hash = hash_entries[0][1]
    for param in pairs:
        param[1] = unquote(param[1])

    pairs.sort(key=lambda x: x[0])
    launch_params = "\n".join(f"{k}={v}" for k, v in pairs if k != "hash")

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, original_hash)


def parse_init_data_user(init_data: str) -> dict[str, Any] | None:
    for part in init_data.split("&"):
        if part.startswith("user="):
            raw = unquote(part[5:])
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


def parse_init_data_auth_date(init_data: str) -> int | None:
    for part in init_data.split("&"):
        if part.startswith("auth_date="):
            try:
                return int(unquote(part.split("=", 1)[1]))
            except ValueError:
                return None
    return None


def init_data_is_fresh(init_data: str, max_age_seconds: int) -> bool:
    auth_date = parse_init_data_auth_date(init_data)
    if auth_date is None:
        return False
    return time.time() - auth_date <= max_age_seconds


def create_access_token(subject: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "access"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    subject: str,
    settings: Settings | None = None,
    *,
    refresh_gen: int = 0,
) -> str:
    settings = settings or get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "refresh", "gen": int(refresh_gen)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_admin_token(subject: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.admin_session_expire_hours)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "admin"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None
