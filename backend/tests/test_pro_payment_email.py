"""Оплата Pro: email для чека без ввода пользователем в MAX."""

from uuid import uuid4

from app.api.payments import _receipt_email_for_user
from app.core.config import Settings
from app.models.user import User


def test_receipt_email_uses_profile_email():
    user = User(id=uuid4(), email="User@Example.com", max_user_id=12345)
    assert _receipt_email_for_user(user, Settings()) == "user@example.com"


def test_receipt_email_auto_for_max_without_email():
    user = User(id=uuid4(), email=None, max_user_id=987654321)
    assert _receipt_email_for_user(user, Settings()) == "max987654321@glosix.ru"


def test_receipt_email_none_without_email_and_max():
    user = User(id=uuid4(), email=None, max_user_id=None)
    assert _receipt_email_for_user(user, Settings()) is None
