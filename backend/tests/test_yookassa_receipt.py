import pytest

from app.services.yookassa import YooKassaError, build_receipt, format_yookassa_error


def test_build_receipt_basic():
    receipt = build_receipt(
        customer_email="user@example.com",
        amount_rub=299,
        description="Glosix Pro — 30 дней",
    )
    assert receipt["customer"] == {"email": "user@example.com"}
    assert len(receipt["items"]) == 1
    item = receipt["items"][0]
    assert item["description"] == "Glosix Pro — 30 дней"
    assert item["quantity"] == "1.00"
    assert item["amount"] == {"value": "299.00", "currency": "RUB"}
    assert item["vat_code"] == 1
    assert item["payment_mode"] == "full_payment"
    assert item["payment_subject"] == "service"
    assert "tax_system_code" not in receipt


def test_build_receipt_with_tax_system_code():
    receipt = build_receipt(
        customer_email=" user@example.com ",
        amount_rub=100,
        description="Test",
        vat_code=2,
        tax_system_code=1,
    )
    assert receipt["customer"]["email"] == "user@example.com"
    assert receipt["items"][0]["vat_code"] == 2
    assert receipt["tax_system_code"] == 1


def test_build_receipt_rejects_invalid_email():
    with pytest.raises(YooKassaError):
        build_receipt(customer_email="", amount_rub=299, description="Pro")


def test_format_yookassa_error_parses_json_description():
    raw = 'HTTP 400: {"type":"error","description":"Receipt is missing or illegal"}'
    assert format_yookassa_error(raw) == "Receipt is missing or illegal"


def test_format_yookassa_error_generic_http():
    assert "поддержку" in format_yookassa_error("HTTP 502: bad gateway")
