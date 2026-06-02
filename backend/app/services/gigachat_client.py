"""OAuth и HTTP для GigaChat API (без официального SDK)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_token: str | None = None
_token_expires_at: float = 0.0


def _ssl_verify(settings: Settings) -> bool | str:
    bundle = (settings.gigachat_ca_bundle_file or "").strip()
    if bundle:
        return bundle
    return settings.gigachat_verify_ssl_certs


def _http_client(settings: Settings, *, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=_ssl_verify(settings))


async def get_access_token(settings: Settings | None = None) -> str:
    global _token, _token_expires_at
    settings = settings or get_settings()
    creds = (settings.gigachat_credentials or "").strip()
    if not creds:
        raise RuntimeError("GIGACHAT_CREDENTIALS не задан")

    now = time.time()
    if _token and now < _token_expires_at - 90:
        return _token

    auth_url = settings.gigachat_auth_url.rstrip("/")
    scope = (settings.gigachat_scope or "GIGACHAT_API_PERS").strip()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {creds}",
    }
    async with _http_client(settings, timeout=30.0) as client:
        resp = await client.post(
            auth_url,
            headers=headers,
            data={"scope": scope},
        )
    if resp.status_code >= 400:
        logger.warning("GigaChat OAuth %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
    data = resp.json()
    access = str(data.get("access_token") or "")
    if not access:
        raise RuntimeError("GigaChat OAuth: пустой access_token")
    expires_in = int(data.get("expires_in") or 1800)
    _token = access
    _token_expires_at = now + max(60, expires_in)
    return access


async def upload_file_bytes(
    data: bytes,
    filename: str,
    *,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    token = await get_access_token(settings)
    base = settings.gigachat_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": (filename, data)}
    form = {"purpose": "general"}
    async with _http_client(settings, timeout=120.0) as client:
        resp = await client.post(
            f"{base}/files",
            headers=headers,
            files=files,
            data=form,
        )
    if resp.status_code >= 400:
        logger.warning("GigaChat upload %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
    body = resp.json()
    file_id = str(body.get("id") or "")
    if not file_id:
        raise RuntimeError("GigaChat upload: нет id файла")
    return file_id


async def chat_completion(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    stream: bool = False,
) -> httpx.Response:
    settings = settings or get_settings()
    token = await get_access_token(settings)
    base = settings.gigachat_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if stream:
        headers["Accept"] = "text/event-stream"
    async with _http_client(settings, timeout=300.0) as client:
        return await client.post(
            f"{base}/chat/completions",
            headers=headers,
            json=payload,
        )


async def iter_chat_stream(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    payload = {**payload, "stream": True}
    settings = settings or get_settings()
    token = await get_access_token(settings)
    base = settings.gigachat_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    async with _http_client(settings, timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                logger.warning("GigaChat stream %s: %s", resp.status_code, body[:500])
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield str(text)


async def download_file_bytes(
    file_id: str,
    *,
    settings: Settings | None = None,
) -> bytes:
    settings = settings or get_settings()
    token = await get_access_token(settings)
    base = settings.gigachat_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/jpeg"}
    async with _http_client(settings, timeout=120.0) as client:
        resp = await client.get(f"{base}/files/{file_id}/content", headers=headers)
    if resp.status_code >= 400:
        logger.warning("GigaChat file download %s: %s", resp.status_code, resp.text[:200])
        resp.raise_for_status()
    return resp.content


async def iter_chat_completion_chunks(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """SSE chunks parsed as JSON objects from GigaChat chat/completions."""
    payload = {**payload, "stream": True}
    settings = settings or get_settings()
    token = await get_access_token(settings)
    base = settings.gigachat_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    async with _http_client(settings, timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                logger.warning("GigaChat stream %s: %s", resp.status_code, body[:500])
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    yield json.loads(chunk)
                except json.JSONDecodeError:
                    continue


async def chat_completion_text(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> str:
    payload = {**payload, "stream": False}
    resp = await chat_completion(payload, settings=settings, stream=False)
    if resp.status_code >= 400:
        logger.warning("GigaChat chat %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return str(msg.get("content") or "").strip()
