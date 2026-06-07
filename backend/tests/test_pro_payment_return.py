from app.api.payments import (
    MAX_PAY_RETURN_START_PARAM,
    _max_payment_return_url,
    _pro_payment_return_url,
)
from app.core.config import Settings
from app.services.subscription_activation import _technical_receipt_email, payment_matches_user
from app.models.user import User
from uuid import uuid4


def test_max_payment_return_url_requires_bot_path():
    assert _max_payment_return_url(Settings(max_bot_url="")) is None
    assert _max_payment_return_url(Settings(max_bot_url="https://max.ru")) is None
    url = _max_payment_return_url(Settings(max_bot_url="https://max.ru/glosix_bot"))
    assert url == f"https://max.ru/glosix_bot?startapp={MAX_PAY_RETURN_START_PARAM}"


def test_pro_payment_return_url_from_max():
    settings = Settings(
        public_web_url="https://glosix.ru",
        max_bot_url="https://max.ru/glosix_bot",
    )
    assert _pro_payment_return_url(settings, from_max=True) == (
        f"https://max.ru/glosix_bot?startapp={MAX_PAY_RETURN_START_PARAM}"
    )


def test_pro_payment_return_url_web_fallback():
    settings = Settings(public_web_url="https://glosix.ru", max_bot_url="")
    assert _pro_payment_return_url(settings, from_max=False) == "https://glosix.ru/profile?payment=success"
    assert _pro_payment_return_url(settings, from_max=True) == "https://glosix.ru/profile?payment=success"


def test_payment_matches_user_by_technical_receipt_email():
    user = User(id=uuid4(), email=None, max_user_id=12345)
    payment = {
        "metadata": {},
        "receipt": {"customer": {"email": "max12345@glosix.ru"}},
    }
    assert payment_matches_user(payment, user) is True
    assert _technical_receipt_email(user, Settings()) == "max12345@glosix.ru"
