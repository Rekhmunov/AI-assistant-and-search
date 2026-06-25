"""Проверки доступа к агентам: Free и Pro + опционально привязанный MAX."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User


def require_agent_eligible(user: User, *, require_max: bool = False) -> None:
    """Agents are open to all registered users (Free + Pro).
    Guests (no email, no plan) are not allowed.
    require_max=True only for MAX-specific agent features.
    """
    if user.guest_key and not user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "agent_auth_required",
                "message": "Зарегистрируйтесь, чтобы использовать агентов.",
            },
        )
    if require_max and user.max_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "agent_max_required",
                "message": "Для запуска агента привяжите аккаунт MAX в профиле.",
            },
        )


def ensure_agent_thread(thread: Thread | None) -> Thread:
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    if thread.thread_type != ThreadType.AGENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "not_agent_thread", "message": "Это не тред агента"},
        )
    return thread


def ensure_search_thread(thread: Thread | None) -> Thread:
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    if thread.thread_type != ThreadType.SEARCH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "wrong_thread_type", "message": "Этот диалог — настройка агента, не поиск."},
        )
    return thread
