import asyncio
import logging
import mimetypes
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.services.bot_message_format import prepare_max_message
from app.services.bot_rate_limit import throttle_max_api

logger = logging.getLogger(__name__)

# https://dev.max.ru/docs-api — platform-api.max.ru, Authorization header, 30 rps
BOT_API_BASE = "https://platform-api.max.ru"

# Пауза после upload перед send (attachment.not.ready — dev.max.ru/docs-api/methods/POST/uploads)
UPLOAD_TO_SEND_DELAY_SEC = 1.0


@dataclass
class BotSendResult:
    ok: bool
    error: str | None = None
    retry_after_sec: float | None = None


class MaxBotService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _auth_headers(self, *, json_body: bool = True) -> dict[str, str]:
        token = self.settings.bot_token.strip()
        headers = {"Authorization": token}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    async def _request_with_rate_limit(self, call):
        await throttle_max_api()
        return await call()

    async def send_message(
        self,
        user_id: int | None,
        text: str,
        attachments: list[dict] | None = None,
        *,
        chat_id: int | None = None,
        text_format: str | None = None,
        notify: bool = True,
        max_attempts: int = 3,
    ) -> BotSendResult:
        if not self.settings.bot_token.strip():
            return BotSendResult(ok=False, error="bot_token not configured")
        if user_id is None and chat_id is None:
            return BotSendResult(ok=False, error="no max_user_id or chat_id")

        text, text_format = prepare_max_message(text, text_format)
        body: dict = {"text": text, "notify": notify}
        if text_format in {"markdown", "html"}:
            body["format"] = text_format
        if attachments:
            body["attachments"] = attachments

        params: dict[str, int] = {}
        if chat_id is not None:
            params["chat_id"] = int(chat_id)
        elif user_id is not None:
            params["user_id"] = int(user_id)

        for attempt in range(max_attempts):
            try:
                async def _post():
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        return await client.post(
                            f"{BOT_API_BASE}/messages",
                            params=params,
                            headers=self._auth_headers(),
                            json=body,
                        )

                response = await self._request_with_rate_limit(_post)
            except httpx.HTTPError as exc:
                logger.warning("MAX send_message network error user_id=%s: %s", user_id, exc)
                return BotSendResult(ok=False, error=str(exc))

            if response.is_success:
                return BotSendResult(ok=True)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 60.0
                except (TypeError, ValueError):
                    delay = 60.0
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(delay, 120.0))
                    continue
                return BotSendResult(ok=False, error="rate_limited", retry_after_sec=delay)

            detail = response.text[:500]
            logger.warning(
                "MAX send_message failed user_id=%s HTTP %s: %s",
                user_id,
                response.status_code,
                detail,
            )
            if "attachment.not.ready" in detail.lower() and attempt + 1 < max_attempts:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue

            return BotSendResult(ok=False, error=detail or f"HTTP {response.status_code}")

        return BotSendResult(ok=False, error="send failed")

    async def delete_message(self, message_id: str, *, max_attempts: int = 2) -> BotSendResult:
        """
        Удаляет сообщение в MAX (DELETE /messages?message_id=…).
        Требует права администратора; по правилам платформы — обычно сообщения младше 24 ч.
        """
        if not self.settings.bot_token.strip():
            return BotSendResult(ok=False, error="bot_token not configured")
        mid = (message_id or "").strip()
        if not mid:
            return BotSendResult(ok=False, error="message_id required")

        for attempt in range(max_attempts):
            try:
                async def _delete():
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        return await client.delete(
                            f"{BOT_API_BASE}/messages",
                            params={"message_id": mid},
                            headers=self._auth_headers(json_body=False),
                        )

                response = await self._request_with_rate_limit(_delete)
            except httpx.HTTPError as exc:
                logger.warning("MAX delete_message network error mid=%s: %s", mid, exc)
                return BotSendResult(ok=False, error=str(exc))

            if response.is_success:
                return BotSendResult(ok=True)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 30.0
                except (TypeError, ValueError):
                    delay = 30.0
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(delay, 120.0))
                    continue
                return BotSendResult(ok=False, error="rate_limited", retry_after_sec=delay)

            detail = response.text[:500]
            logger.warning(
                "MAX delete_message failed mid=%s HTTP %s: %s",
                mid,
                response.status_code,
                detail,
            )
            return BotSendResult(ok=False, error=detail or f"HTTP {response.status_code}")

        return BotSendResult(ok=False, error="delete failed")

    async def upload_media(self, data: bytes, filename: str, media_type: str) -> str | None:
        """Upload image or video to MAX and return attachment token."""
        if not self.settings.bot_token.strip():
            return None
        if media_type not in {"image", "video"}:
            return None

        headers = self._auth_headers(json_body=False)

        async def _init_upload():
            async with httpx.AsyncClient(timeout=120.0) as client:
                return await client.post(
                    f"{BOT_API_BASE}/uploads",
                    params={"type": media_type},
                    headers=headers,
                )

        upload_resp = await self._request_with_rate_limit(_init_upload)
        if not upload_resp.is_success:
            logger.warning("MAX upload init failed: %s", upload_resp.text[:300])
            return None

        body = upload_resp.json()
        upload_url = body.get("url")
        token = body.get("token")
        if not upload_url:
            return str(token) if token else None

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async def _upload_file():
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Multipart upload на CDN URL — без Authorization (dev.max.ru/docs-api/methods/POST/uploads).
                return await client.post(
                    upload_url,
                    headers={"Content-Type": "multipart/form-data"},
                    files={"data": (filename, data, content_type)},
                )

        put_resp = await _upload_file()
        if not put_resp.is_success:
            logger.warning("MAX upload POST failed: %s", put_resp.text[:300])
            return str(token) if token else None

        try:
            put_body = put_resp.json()
            if isinstance(put_body, dict) and put_body.get("token"):
                return str(put_body["token"])
        except ValueError:
            pass

        return str(token) if token else None
