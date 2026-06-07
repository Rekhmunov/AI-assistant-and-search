import pytest

from app.core.limiter import RateLimiter
from app.models.user import Plan, User


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    async def get(self, key: str):
        return str(self.store[key]) if key in self.store else None

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key: str) -> int:
        self.store[key] = max(0, self.store.get(key, 0) - 1)
        return self.store[key]

    async def expireat(self, *_args, **_kwargs):
        return True


def _guest_user(user_id: str = "guest-1") -> User:
    import uuid

    return User(id=uuid.UUID(int=1), guest_key="gk", plan=Plan.FREE)


@pytest.mark.asyncio
async def test_guest_search_limit_is_lifetime_not_daily():
    redis = _FakeRedis()
    limiter = RateLimiter(redis)
    limiter.settings.guest_searches_per_day = 5
    guest = _guest_user()
    uid = str(guest.id)

    for i in range(1, 6):
        ok, used, limit = await limiter.check_search_limit(uid, guest.plan, guest)
        assert ok is True
        assert used == i
        assert limit == 5

    ok, used, limit = await limiter.check_search_limit(uid, guest.plan, guest)
    assert ok is False
    assert used == 5
    assert limit == 5

    usage = await limiter.get_search_usage(uid, guest)
    assert usage == 5
