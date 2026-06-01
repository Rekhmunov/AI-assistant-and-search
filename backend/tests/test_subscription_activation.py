import uuid
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import Plan, User
from app.services.subscription_activation import (
    activate_from_yookassa_payment,
    payment_matches_user,
    recover_pro_for_user,
)


class TestSubscriptionActivation(unittest.IsolatedAsyncioTestCase):
    def _mock_db(self):
        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_activate_from_payment_by_subscription(self):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        sub = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-123",
            status=SubscriptionStatus.PENDING,
            amount_rub=999,
        )

        db = self._mock_db()
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = sub
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(side_effect=[sub_result, user_result])

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

        db = self._mock_db()
        missing = MagicMock()
        missing.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(side_effect=[missing, user_result])
        db.add = MagicMock()

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

    async def test_payment_matches_user_by_receipt_email(self):
        user = User(id=uuid.uuid4(), plan=Plan.FREE, email="Paid@Yandex.ru")
        payment = {
            "status": "succeeded",
            "metadata": {},
            "receipt": {"customer": {"email": "paid@yandex.ru"}},
        }
        self.assertTrue(payment_matches_user(payment, user))

    async def test_activate_syncs_user_when_subscription_already_active(self):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        sub = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-active",
            status=SubscriptionStatus.ACTIVE,
            amount_rub=99,
            activated_at=datetime.now(timezone.utc),
        )

        db = self._mock_db()
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = sub
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(side_effect=[sub_result, user_result])

        ok = await activate_from_yookassa_payment(
            db,
            payment_id="pay-active",
            payment_object={"status": "succeeded", "metadata": {"user_id": str(user_id)}},
        )
        self.assertTrue(ok)
        self.assertEqual(user.plan, Plan.PRO)
        self.assertIsNotNone(user.plan_expires_at)

    async def test_recover_resyncs_from_active_subscription(self):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        active_sub = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-active",
            status=SubscriptionStatus.ACTIVE,
            amount_rub=99,
            activated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )

        all_subs_result = MagicMock()
        all_subs_result.scalars.return_value.all.return_value = [active_sub]
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = active_sub
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        db = self._mock_db()
        db.execute = AsyncMock(side_effect=[all_subs_result, sub_result, user_result])

        with patch("app.services.subscription_activation.get_payment", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status": "succeeded", "id": "pay-active"}
            result = await recover_pro_for_user(db, user)

        self.assertTrue(result["ok"])
        self.assertEqual(result.get("source"), "subscription_record")
        self.assertEqual(user.plan, Plan.PRO)

    async def test_recover_skips_yookassa_when_already_pro(self):
        user = User(id=uuid.uuid4(), plan=Plan.PRO, email="a@b.c")
        db = MagicMock()
        result = await recover_pro_for_user(db, user)
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("already_active"))
        db.execute.assert_not_called()

    @patch("app.services.subscription_activation.list_all_payments", new_callable=AsyncMock)
    @patch("app.services.subscription_activation.get_payment", new_callable=AsyncMock)
    async def test_recover_from_yookassa_scan_when_pending_not_paid(self, mock_get_payment, mock_list_all):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="paid@yandex.ru")
        old_pending = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-new-unpaid",
            status=SubscriptionStatus.PENDING,
            amount_rub=99,
            created_at=datetime.now(timezone.utc),
        )

        all_subs_result = MagicMock()
        all_subs_result.scalars.return_value.all.return_value = [old_pending]
        missing_sub = MagicMock()
        missing_sub.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        active_sub = MagicMock()
        active_sub.scalar_one_or_none.return_value = old_pending

        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[all_subs_result, missing_sub, user_result, active_sub]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        mock_get_payment.return_value = {"status": "pending", "id": "pay-new-unpaid"}
        mock_list_all.side_effect = [
            [],
            [
                {
                    "id": "pay-real-success",
                    "status": "succeeded",
                    "metadata": {"user_id": str(user_id)},
                    "amount": {"value": "99.00", "currency": "RUB"},
                }
            ],
        ]

        result = await recover_pro_for_user(db, user)
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("source"), "yookassa_scan")
        self.assertEqual(result.get("payment_id"), "pay-real-success")
        self.assertEqual(user.plan, Plan.PRO)

    @patch("app.services.subscription_activation.list_all_payments", new_callable=AsyncMock)
    @patch("app.services.subscription_activation.get_payment", new_callable=AsyncMock)
    async def test_recover_does_not_show_processing_for_old_pending(self, mock_get_payment, mock_list_all):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        old_pending = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-old-pending",
            status=SubscriptionStatus.PENDING,
            amount_rub=99,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        all_subs_result = MagicMock()
        all_subs_result.scalars.return_value.all.return_value = [old_pending]

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[all_subs_result])
        mock_get_payment.return_value = {"status": "pending", "id": "pay-old-pending"}
        mock_list_all.side_effect = [[], []]

        result = await recover_pro_for_user(db, user)
        self.assertFalse(result["ok"])
        self.assertNotIn("обрабатывается", result.get("message", ""))

    @patch("app.services.subscription_activation.get_payment", new_callable=AsyncMock)
    async def test_recover_from_pending_subscription(self, mock_get_payment):
        user_id = uuid.uuid4()
        user = User(id=user_id, plan=Plan.FREE, email="a@b.c")
        sub = Subscription(
            user_id=user_id,
            yookassa_payment_id="pay-789",
            status=SubscriptionStatus.PENDING,
            amount_rub=99,
            created_at=datetime.now(timezone.utc),
        )

        all_subs_result = MagicMock()
        all_subs_result.scalars.return_value.all.return_value = [sub]
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = sub
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        db = self._mock_db()
        db.execute = AsyncMock(side_effect=[all_subs_result, sub_result, user_result])
        mock_get_payment.return_value = {
            "status": "succeeded",
            "id": "pay-789",
            "metadata": {"user_id": str(user_id)},
        }

        with patch("app.services.subscription_activation.list_all_payments", new_callable=AsyncMock) as mock_list:
            result = await recover_pro_for_user(db, user)
            mock_list.assert_not_called()

        self.assertTrue(result["ok"])
        self.assertEqual(result.get("source"), "subscription_record")
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
