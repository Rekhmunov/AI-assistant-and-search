import asyncio
import logging
import mimetypes
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

BOT_API_BASE = "https://botapi.max.ru"


@dataclass
class BotSendResult:
    ok: bool
    error: str | None = None
    retry_after_sec: float | None = None


class MaxBotService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _auth_params(self) -> dict[str, str]:
        return {"access_token": self.settings.bot_token}

    async def send_message(
        self,
        user_id: int | None,
        text: str,
        attachments: list[dict] | None = None,
        *,
        max_attempts: int = 3,
    ) -> BotSendResult:
        if not self.settings.bot_token:
            return BotSendResult(ok=False, error="bot_token not configured")
        if user_id is None:
            return BotSendResult(ok=False, error="no max_user_id")

        payload: dict = {"user_id": user_id, "text": text}
        if attachments:
            payload["attachments"] = attachments

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{BOT_API_BASE}/messages",
                        params=self._auth_params(),
                        json=payload,
                    )
            except httpx.HTTPError as exc:
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

            detail = response.text[:300]
            if "attachment.not.ready" in detail.lower() and attempt + 1 < max_attempts:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue

            return BotSendResult(ok=False, error=detail or f"HTTP {response.status_code}")

        return BotSendResult(ok=False, error="send failed")

    async def upload_media(self, data: bytes, filename: str, media_type: str) -> str | None:
        """Upload image or video to MAX and return attachment token."""
        if not self.settings.bot_token:
            return None
        if media_type not in {"image", "video"}:
            return None

        params = {**self._auth_params(), "type": media_type}
        async with httpx.AsyncClient(timeout=120.0) as client:
            upload_resp = await client.post(f"{BOT_API_BASE}/uploads", params=params)
            if not upload_resp.is_success:
                logger.warning("MAX upload init failed: %s", upload_resp.text[:300])
                return None

            body = upload_resp.json()
            upload_url = body.get("url")
            token = body.get("token")
            if not upload_url:
                return token

            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            put_resp = await client.put(upload_url, content=data, headers={"Content-Type": content_type})
            if not put_resp.is_success:
                logger.warning("MAX upload PUT failed: %s", put_resp.text[:300])
                return None

            if token:
                return str(token)

            # Some responses embed token only after PUT — re-read from URL fragment/query if needed.
            return body.get("token")
