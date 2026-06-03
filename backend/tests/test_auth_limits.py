import asyncio

from app.core.auth_limits import check_auth_rate_limit, clear_auth_rate_limit


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, _sec: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def test_check_auth_rate_limit_key_format():
    redis = _FakeRedis()
    asyncio.run(check_auth_rate_limit(redis, "register", "1.2.3.4"))
    assert "auth_attempts:register:1.2.3.4" in redis.store


def test_clear_auth_rate_limit():
    redis = _FakeRedis()
    asyncio.run(check_auth_rate_limit(redis, "register_email", "User@Mail.COM"))
    key = "auth_attempts:register_email:user@mail.com"
    assert redis.store.get(key) == 1
    asyncio.run(clear_auth_rate_limit(redis, "register_email", "user@mail.com"))
    assert key not in redis.store
