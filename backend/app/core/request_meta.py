"""Метаданные HTTP-запроса для аудита согласий."""

from __future__ import annotations

from fastapi import Request

from app.core.auth_limits import client_ip


def user_agent(request: Request, *, max_len: int = 512) -> str | None:
    raw = (request.headers.get("user-agent") or "").strip()
    if not raw:
        return None
    return raw[:max_len]


def consent_request_meta(request: Request) -> tuple[str | None, str | None]:
    return client_ip(request), user_agent(request)
