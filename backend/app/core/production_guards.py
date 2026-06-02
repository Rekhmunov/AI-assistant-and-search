"""Startup checks that must pass in production."""

from __future__ import annotations

from app.core.config import Settings

_DEFAULT_JWT_SECRET = "change-me-in-production"


def assert_production_security(settings: Settings) -> None:
    """Fail fast when production is deployed with unsafe defaults."""
    if settings.environment.strip().lower() != "production":
        return

    secret = settings.jwt_secret.strip()
    if not secret or secret == _DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET must be set to a strong random value in production "
            "(default 'change-me-in-production' is not allowed)."
        )
