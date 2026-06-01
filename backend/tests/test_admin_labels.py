import unittest

from app.models.subscription import SubscriptionStatus
from app.services.admin_labels import format_admin_user_label, subscription_status_label


class DummyUser:
    def __init__(self, **kwargs):
        self.email = kwargs.get("email")
        self.username = kwargs.get("username")
        self.max_user_id = kwargs.get("max_user_id")
        self.first_name = kwargs.get("first_name")
        self.last_name = kwargs.get("last_name")
        self.id = kwargs.get("id", "00000000-0000-0000-0000-000000000001")


class TestAdminLabels(unittest.TestCase):
    def test_subscription_status_label_russian(self):
        self.assertEqual(subscription_status_label(SubscriptionStatus.PENDING), "Ожидает оплаты")
        self.assertEqual(subscription_status_label("active"), "Активна")

    def test_format_user_label_prefers_email(self):
        user = DummyUser(email="test@yandex.ru", max_user_id=None, username="oksana")
        self.assertEqual(format_admin_user_label(user), "test@yandex.ru")

    def test_format_user_contacts_shows_email_and_max(self):
        user = DummyUser(email="test@yandex.ru", max_user_id=13294341)
        from app.services.admin_labels import format_admin_user_contacts

        self.assertEqual(
            format_admin_user_contacts(user),
            "email: test@yandex.ru, max: 13294341",
        )

    def test_format_user_contacts_shows_unlinked(self):
        from app.services.admin_labels import format_admin_user_contacts

        user = DummyUser(email=None, max_user_id=None)
        self.assertEqual(format_admin_user_contacts(user), "email: не привязан, max: не привязан")


if __name__ == "__main__":
    unittest.main()
