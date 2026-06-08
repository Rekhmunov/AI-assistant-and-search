from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.user import Plan, User


@pytest.mark.asyncio
async def test_login_clears_legacy_deleted_max_user_id(monkeypatch):
    """Deleted account that still holds max_user_id must not block re-registration."""
    from app.api import auth as auth_module

    max_user_id = 424242
    legacy_id = uuid4()
    legacy_user = User(id=legacy_id, max_user_id=max_user_id, deleted_at=datetime.now(timezone.utc))

    active_result = MagicMock()
    active_result.scalar_one_or_none.return_value = None

    legacy_result = MagicMock()
    legacy_result.scalar_one_or_none.return_value = legacy_user

    created_user = User(
        id=uuid4(),
        max_user_id=max_user_id,
        first_name="A",
        language="ru",
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[active_result, legacy_result])

    async def _flush():
        if created_user.id is None:
            created_user.id = uuid4()

    db.flush = AsyncMock(side_effect=_flush)

    def _add(user: User) -> None:
        if user is not legacy_user:
            user.id = created_user.id
            user.plan = Plan.FREE
            user.language = created_user.language

    db.add = MagicMock(side_effect=_add)

    limiter = AsyncMock()
    limiter.usage_and_limit = AsyncMock(return_value=(0, 10))
    redis_client = AsyncMock()
    response = MagicMock()

    monkeypatch.setattr(auth_module, "get_settings", lambda: MagicMock(skip_init_data_validation=True, bot_token="x"))
    monkeypatch.setattr(auth_module, "parse_init_data_user", lambda _d: {"id": max_user_id, "first_name": "A"})
    monkeypatch.setattr(auth_module, "_merge_guest_session", AsyncMock())
    monkeypatch.setattr(auth_module, "_set_auth_cookies", AsyncMock(return_value="access"))
    monkeypatch.setattr(auth_module, "clear_guest_cookie", lambda _r: None)

    request = MagicMock()
    body = MagicMock(init_data="dev")

    result = await auth_module.login(
        request=request,
        body=body,
        response=response,
        db=db,
        limiter=limiter,
        redis_client=redis_client,
        guest_session=None,
    )

    assert legacy_user.max_user_id is None
    db.add.assert_called_once()
    new_user = db.add.call_args[0][0]
    assert new_user.max_user_id == max_user_id
    assert result.access_token == "access"
