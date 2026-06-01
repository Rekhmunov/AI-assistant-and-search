"""Подписи для админки (русский UI)."""

from __future__ import annotations

from app.models.subscription import SubscriptionStatus
from app.models.user import User

SUBSCRIPTION_STATUS_LABELS: dict[str, str] = {
    SubscriptionStatus.PENDING.value: "Ожидает оплаты",
    SubscriptionStatus.ACTIVE.value: "Активна",
    SubscriptionStatus.CANCELED.value: "Отменена",
    SubscriptionStatus.FAILED.value: "Ошибка",
}


def subscription_status_label(status: str | SubscriptionStatus) -> str:
    raw = status.value if isinstance(status, SubscriptionStatus) else str(status)
    return SUBSCRIPTION_STATUS_LABELS.get(raw, raw)


def format_admin_user_label(user: User) -> str:
    if user.email:
        return user.email
    if user.username:
        return f"@{user.username}"
    if user.max_user_id is not None:
        return f"MAX {user.max_user_id}"
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name = f"{name} {user.last_name}"
        return name
    return str(user.id)
