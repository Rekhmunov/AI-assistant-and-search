import httpx

from app.core.config import Settings, get_settings

BOT_API_BASE = "https://botapi.max.ru"


class MaxBotService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def send_message(self, user_id: int, text: str) -> bool:
        if not self.settings.bot_token:
            return False

        params = {"access_token": self.settings.bot_token}
        payload = {"user_id": user_id, "text": text}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{BOT_API_BASE}/messages", params=params, json=payload)
            return response.is_success
