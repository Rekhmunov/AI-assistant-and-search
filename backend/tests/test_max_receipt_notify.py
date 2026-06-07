import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import Plan, User
from app.services.subscription_activation import (
    _send_max_receipt_link,
    notify_max_pro_payment_success,
)


class TestMaxReceiptNotify(unittest.IsolatedAsyncioTestCase):
    async def test_notify_sends_activation_and_schedules_receipt(self):
        user = User(id=uuid.uuid4(), plan=Plan.FREE, max_user_id=12345)

        with (
            patch(
                "app.services.subscription_activation._max_pro_notify_lock",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_notify_lock,
            patch(
                "app.services.subscription_activation._max_pro_receipt_lock",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_receipt_lock,
            patch(
                "app.services.subscription_activation.MaxBotService"
            ) as mock_bot_cls,
            patch("app.services.subscription_activation.asyncio.create_task") as mock_create_task,
        ):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(return_value=MagicMock(ok=True))
            mock_bot_cls.return_value = mock_bot

            await notify_max_pro_payment_success(user, payment_id="pay-123")

        mock_notify_lock.assert_awaited_once_with("pay-123")
        mock_receipt_lock.assert_awaited_once_with("pay-123")
        mock_bot.send_message.assert_awaited_once_with(12345, "Подписка Pro активирована 🎉")
        mock_create_task.assert_called_once()

    async def test_notify_skips_without_max_user_id(self):
        user = User(id=uuid.uuid4(), plan=Plan.FREE, max_user_id=None)

        with patch("app.services.subscription_activation.MaxBotService") as mock_bot_cls:
            await notify_max_pro_payment_success(user, payment_id="pay-123")
            mock_bot_cls.assert_not_called()

    async def test_notify_dedupes_repeat_payment(self):
        user = User(id=uuid.uuid4(), plan=Plan.FREE, max_user_id=99)

        with (
            patch(
                "app.services.subscription_activation._max_pro_notify_lock",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("app.services.subscription_activation.MaxBotService") as mock_bot_cls,
        ):
            await notify_max_pro_payment_success(user, payment_id="pay-dup")
            mock_bot_cls.assert_not_called()

    async def test_send_max_receipt_link_posts_markdown_link(self):
        with (
            patch(
                "app.services.subscription_activation.get_receipt_url_for_payment",
                new_callable=AsyncMock,
                return_value="https://ofd.example/check/42",
            ),
            patch("app.services.subscription_activation.MaxBotService") as mock_bot_cls,
        ):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(return_value=MagicMock(ok=True))
            mock_bot_cls.return_value = mock_bot

            await _send_max_receipt_link(777, "pay-777", settings=MagicMock())

        mock_bot.send_message.assert_awaited_once_with(
            777,
            "[Чек об оплате](https://ofd.example/check/42)",
            text_format="markdown",
        )


if __name__ == "__main__":
    unittest.main()
