from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.user import User
from app.services.account_purge import purge_expired_deleted_accounts


@pytest.mark.asyncio
async def test_purge_only_users_deleted_longer_than_retention():
    now = datetime.now(timezone.utc)
    old_deleted = User(id=uuid4(), deleted_at=now - timedelta(days=91))
    recent_deleted = User(id=uuid4(), deleted_at=now - timedelta(days=10))

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [old_deleted])))
    )
    redis_client = AsyncMock()

    with patch("app.services.account_purge.purge_user_account", new_callable=AsyncMock) as purge_one:
        count = await purge_expired_deleted_accounts(db, redis_client, retention_days=90)

    assert count == 1
    purge_one.assert_awaited_once_with(db, redis_client, old_deleted)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_purge_skips_when_retention_zero():
    db = AsyncMock()
    redis_client = AsyncMock()
    count = await purge_expired_deleted_accounts(db, redis_client, retention_days=0)
    assert count == 0
    db.execute.assert_not_called()
