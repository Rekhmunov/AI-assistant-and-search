import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.providers.llm_fallback import ClaudeWithYandexFallback
from app.services.yandex_errors import YandexServiceError


class TestClaudeFallback(unittest.IsolatedAsyncioTestCase):
    async def test_complete_text_falls_back_to_yandex(self):
        primary = MagicMock()
        primary.complete_text = AsyncMock(
            side_effect=YandexServiceError("gpt", "403 Request not allowed", 403)
        )
        fallback = MagicMock()
        fallback.complete_text = AsyncMock(return_value='{"needs_search": true}')
        fallback.settings = MagicMock(yandex_configured=True)

        llm = ClaudeWithYandexFallback(primary, fallback)
        text = await llm.complete_text([{"role": "user", "text": "hi"}])
        self.assertIn("needs_search", text)
        fallback.complete_text.assert_awaited_once()

    async def test_complete_text_no_fallback_without_yandex(self):
        primary = MagicMock()
        primary.complete_text = AsyncMock(
            side_effect=YandexServiceError("gpt", "403", 403)
        )
        fallback = MagicMock()
        fallback.settings = MagicMock(yandex_configured=False)

        llm = ClaudeWithYandexFallback(primary, fallback)
        with self.assertRaises(YandexServiceError):
            await llm.complete_text([{"role": "user", "text": "hi"}])


if __name__ == "__main__":
    unittest.main()
