import asyncio
import logging
import mimetypes
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.services.bot_message_format import prepare_max_message

logger = logging.getLogger(__name__)

# https://dev.max.ru/docs-api — platform-api.max.ru, Authorization header
BOT_API_BASE = "https://platform-api.max.ru"


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

    async def send_message(
        self,
        user_id: int | None,
        text: str,
        attachments: list[dict] | None = None,
        *,
        text_format: str | None = None,
        max_attempts: int = 3,
    ) -> BotSendResult:
        if not self.settings.bot_token.strip():
            return BotSendResult(ok=False, error="bot_token not configured")
        if user_id is None:
            return BotSendResult(ok=False, error="no max_user_id")

        text, text_format = prepare_max_message(text, text_format)
        body: dict = {"text": text}
        if text_format in {"markdown", "html"}:
            body["format"] = text_format
        if attachments:
            body["attachments"] = attachments

        params = {"user_id": int(user_id)}

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{BOT_API_BASE}/messages",
                        params=params,
                        headers=self._auth_headers(),
                        json=body,
                    )
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

    async def upload_media(self, data: bytes, filename: str, media_type: str) -> str | None:
        """Upload image or video to MAX and return attachment token."""
        if not self.settings.bot_token.strip():
            return None
        if media_type not in {"image", "video"}:
            return None

        headers = self._auth_headers(json_body=False)
        async with httpx.AsyncClient(timeout=120.0) as client:
            upload_resp = await client.post(
                f"{BOT_API_BASE}/uploads",
                params={"type": media_type},
                headers=headers,
            )
            if not upload_resp.is_success:
                logger.warning("MAX upload init failed: %s", upload_resp.text[:300])
                return None

            body = upload_resp.json()
            upload_url = body.get("url")
            token = body.get("token")
            if not upload_url:
                return str(token) if token else None

            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            put_resp = await client.post(
                upload_url,
                headers={"Content-Type": "multipart/form-data"},
                files={"data": (filename, data, content_type)},
            )
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
