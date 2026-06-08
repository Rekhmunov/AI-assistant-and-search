from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.user import Plan, User


def _login_db_for_reactivation(deleted_user: User, *, flush_raises: bool = False):
    active_result = MagicMock()
    active_result.scalar_one_or_none.return_value = None

    deleted_result = MagicMock()
    deleted_result.scalar_one_or_none.return_value = deleted_user

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[active_result, deleted_result])
    if flush_raises:
        db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
        db.rollback = AsyncMock()
    else:
        db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_login_reactivates_self_deleted_max_account():
    from app.api import auth as auth_module

    max_user_id = 424242
    deleted_user = User(
        id=uuid4(),
        max_user_id=max_user_id,
        deleted_at=datetime.now(timezone.utc),
        plan=Plan.FREE,
        language="ru",
    )
    db = _login_db_for_reactivation(deleted_user)

    user = await auth_module._resolve_max_login_user(
        db,
        max_user_id,
        {"id": max_user_id, "first_name": "New", "language_code": "ru"},
    )

    assert user is deleted_user
    assert user.deleted_at is None
    assert user.first_name == "New"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_login_creates_new_user_when_deleted_max_id_was_cleared(monkeypatch):
    from app.api import auth as auth_module

    max_user_id = 424242
    active_result = MagicMock()
    active_result.scalar_one_or_none.return_value = None
    deleted_result = MagicMock()
    deleted_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[active_result, deleted_result, active_result])
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()

    user = await auth_module._resolve_max_login_user(
        db,
        max_user_id,
        {"id": max_user_id, "first_name": "A", "language_code": "ru"},
    )

    db.add.assert_called_once()
    created = db.add.call_args[0][0]
    assert created.max_user_id == max_user_id
    assert user is created

