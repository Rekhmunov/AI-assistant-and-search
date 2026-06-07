"""Оплата Pro: email для пользователей MAX без привязанного email."""

from pathlib import Path


def test_create_payment_accepts_customer_email_in_schema():
    src = Path(__file__).resolve().parents[1] / "app/schemas/payments.py"
    text = src.read_text(encoding="utf-8")
    assert "customer_email" in text


def test_create_payment_saves_email_for_max_user():
    src = Path(__file__).resolve().parents[1] / "app/api/payments.py"
    text = src.read_text(encoding="utf-8")
    assert "body.customer_email" in text
    assert "user.max_user_id is None" in text
