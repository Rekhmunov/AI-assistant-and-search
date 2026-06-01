"""Создание платежей YooKassa (REST API v3)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


class YooKassaError(Exception):
    pass


async def create_payment(
    *,
    amount_rub: int,
    description: str,
    return_url: str,
    metadata: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    shop_id = settings.yookassa_shop_id.strip()
    secret = settings.yookassa_secret_key.strip()
    if not shop_id or not secret:
        raise YooKassaError("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")

    payload: dict[str, Any] = {
        "amount": {"value": f"{int(amount_rub)}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description[:128],
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

    data = resp.json()
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
