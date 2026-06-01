import uuid
import unittest
from unittest.mock import AsyncMock, MagicMock

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import Plan, User
from app.services.subscription_activation import activate_from_yookassa_payment


class TestSubscriptionActivation(unittest.IsolatedAsyncioTestCase):
    async def test_activate_from_payment_by_subscription(self):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        sub = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-123",
            status=SubscriptionStatus.PENDING,
            amount_rub=999,
        )

        db = MagicMock()
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = sub
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(side_effect=[sub_result, user_result])
        db.flush = AsyncMock()

        ok = await activate_from_yookassa_payment(
            db,
            payment_id="pay-123",
            payment_object={"status": "succeeded"},
        )
        self.assertTrue(ok)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(user.plan, Plan.PRO)
        self.assertIsNotNone(user.plan_expires_at)

    async def test_activate_creates_subscription_from_metadata_if_missing(self):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")

        db = MagicMock()
        missing = MagicMock()
        missing.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(side_effect=[missing, user_result])
        db.add = MagicMock()
        db.flush = AsyncMock()

        ok = await activate_from_yookassa_payment(
            db,
            payment_id="pay-456",
            payment_object={
                "status": "succeeded",
                "metadata": {"user_id": str(user_id)},
                "amount": {"value": "999.00", "currency": "RUB"},
            },
        )
        self.assertTrue(ok)
        db.add.assert_called_once()
        self.assertEqual(user.plan, Plan.PRO)


if __name__ == "__main__":
    unittest.main()
