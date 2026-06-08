from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import hash_password
from app.models.user import Plan, User


@pytest.mark.asyncio
async def test_login_email_reactivates_self_deleted_account():
    from app.api import auth as auth_module

    email = "user@example.com"
    password = "secretpass123"
    deleted_user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_password(password),
        deleted_at=datetime.now(timezone.utc),
        plan=Plan.FREE,
        language="ru",
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=deleted_user))
    )

    limiter = AsyncMock()
    limiter.usage_and_limit = AsyncMock(return_value=(0, 10))
    redis_client = AsyncMock()
    response = MagicMock()

    monkeypatch_targets = {
        "verify_allowed_origin": lambda _r: None,
        "check_auth_rate_limit": AsyncMock(),
        "clear_auth_rate_limit": AsyncMock(),
        "_merge_guest_session": AsyncMock(),
        "_set_auth_cookies": AsyncMock(return_value="access"),
        "clear_guest_cookie": lambda _r: None,
    }
    for name, value in monkeypatch_targets.items():
        setattr(auth_module, name, value)

    body = MagicMock(email=email, password=password)
    result = await auth_module.login_email(
        request=MagicMock(),
        body=body,
        response=response,
        db=db,
        limiter=limiter,
        redis_client=redis_client,
        guest_session=None,
    )

    assert deleted_user.deleted_at is None
    assert result.access_token == "access"


@pytest.mark.asyncio
async def test_login_email_rejects_admin_banned_account():
    from app.api import auth as auth_module

    banned_user = User(
        id=uuid4(),
        email="banned@example.com",
        password_hash=None,
        deleted_at=datetime.now(timezone.utc),
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=banned_user))
    )

    auth_module.verify_allowed_origin = lambda _r: None
    auth_module.check_auth_rate_limit = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await auth_module.login_email(
            request=MagicMock(),
            body=MagicMock(email="banned@example.com", password="any"),
            response=MagicMock(),
            db=db,
            limiter=AsyncMock(),
            redis_client=AsyncMock(),
        )

    assert exc.value.status_code == 401


def test_reactivate_keeps_pro_until_expiry():
    from app.api.auth import _reactivate_self_deleted_user

    user = User(
        id=uuid4(),
        deleted_at=datetime.now(timezone.utc),
        plan=Plan.PRO,
        plan_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    _reactivate_self_deleted_user(user)
    assert user.deleted_at is None
    assert user.plan == Plan.PRO


def test_reactivate_downgrades_expired_pro():
    from app.api.auth import _reactivate_self_deleted_user

    user = User(
        id=uuid4(),
        deleted_at=datetime.now(timezone.utc),
        plan=Plan.PRO,
        plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    _reactivate_self_deleted_user(user)
    assert user.plan == Plan.FREE
    assert user.plan_expires_at is None
