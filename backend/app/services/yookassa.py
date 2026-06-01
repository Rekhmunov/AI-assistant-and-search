"""Создание платежей YooKassa (REST API v3)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


class YooKassaError(Exception):
    pass


def build_receipt(
    *,
    customer_email: str,
    amount_rub: int,
    description: str,
    vat_code: int = 1,
    tax_system_code: int | None = None,
) -> dict[str, Any]:
    """Build fiscal receipt payload required by YooKassa (54-FZ)."""
    email = customer_email.strip()
    if not email or "@" not in email:
        raise YooKassaError("Для чека нужен корректный email покупателя")

    receipt: dict[str, Any] = {
        "customer": {"email": email},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": f"{int(amount_rub)}.00", "currency": "RUB"},
                "vat_code": int(vat_code),
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }
    if tax_system_code is not None:
        receipt["tax_system_code"] = int(tax_system_code)
    return receipt


async def create_payment(
    *,
    amount_rub: int,
    description: str,
    return_url: str,
    customer_email: str,
    metadata: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    shop_id = settings.yookassa_shop_id.strip()
    secret = settings.yookassa_secret_key.strip()
    if not shop_id or not secret:
        raise YooKassaError("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")

    tax_system_code: int | None = None
    if settings.yookassa_tax_system_code:
        tax_system_code = settings.yookassa_tax_system_code

    payload: dict[str, Any] = {
        "amount": {"value": f"{int(amount_rub)}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description[:128],
        "receipt": build_receipt(
            customer_email=customer_email,
            amount_rub=amount_rub,
            description=description,
            vat_code=settings.yookassa_vat_code,
            tax_system_code=tax_system_code,
        ),
    }
    if metadata:
        payload["metadata"] = metadata

    headers = {"Idempotence-Key": str(uuid.uuid4()), "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                YOOKASSA_API,
                json=payload,
                auth=(shop_id, secret),
                headers=headers,
            )
    except httpx.HTTPError as e:
        logger.exception("YooKassa create payment network error")
        raise YooKassaError(f"Сеть: {e}") from e

    if resp.status_code >= 400:
        detail = (resp.text or "")[:400]
        logger.warning("YooKassa create payment HTTP %s: %s", resp.status_code, detail)
        raise YooKassaError(f"HTTP {resp.status_code}: {detail}")

    try:
        data = resp.json()
    except ValueError as e:
        snippet = (resp.text or "")[:200]
        raise YooKassaError(f"Некорректный ответ YooKassa: {snippet}") from e

    confirmation = data.get("confirmation") or {}
    url = confirmation.get("confirmation_url")
    payment_id = data.get("id")
    if not payment_id or not url:
        raise YooKassaError("YooKassa: нет id или confirmation_url в ответе")
    return {
        "payment_id": str(payment_id),
        "confirmation_url": str(url),
        "status": data.get("status"),
    }


async def get_payment(
    payment_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    shop_id = settings.yookassa_shop_id.strip()
    secret = settings.yookassa_secret_key.strip()
    if not shop_id or not secret:
        raise YooKassaError("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")

    url = f"{YOOKASSA_API}/{payment_id}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(url, auth=(shop_id, secret))
    except httpx.HTTPError as e:
        logger.exception("YooKassa get payment network error")
        raise YooKassaError(f"Сеть: {e}") from e

    if resp.status_code >= 400:
        detail = (resp.text or "")[:400]
        raise YooKassaError(f"HTTP {resp.status_code}: {detail}")

    try:
        return resp.json()
    except ValueError as e:
        snippet = (resp.text or "")[:200]
        raise YooKassaError(f"Некорректный ответ YooKassa: {snippet}") from e


async def list_payments(
    *,
    created_gte: datetime,
    limit: int = 100,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """List YooKassa payments (newest first) from a given date."""
    settings = settings or get_settings()
    shop_id = settings.yookassa_shop_id.strip()
    secret = settings.yookassa_secret_key.strip()
    if not shop_id or not secret:
        raise YooKassaError("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")

    params = {
        "created_at.gte": created_gte.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": min(max(limit, 1), 100),
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(
                YOOKASSA_API,
                params=params,
                auth=(shop_id, secret),
            )
    except httpx.HTTPError as e:
        logger.exception("YooKassa list payments network error")
        raise YooKassaError(f"Сеть: {e}") from e

    if resp.status_code >= 400:
        detail = (resp.text or "")[:400]
        raise YooKassaError(f"HTTP {resp.status_code}: {detail}")

    try:
        data = resp.json()
    except ValueError as e:
        snippet = (resp.text or "")[:200]
        raise YooKassaError(f"Некорректный ответ YooKassa: {snippet}") from e

    items = data.get("items")
    return items if isinstance(items, list) else []
