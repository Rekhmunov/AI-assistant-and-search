import asyncio
from uuid import uuid4

from app.services.max_bind_token import (
    BIND_TOKEN_TTL_SEC,
    consume_max_bind_token,
    create_max_bind_token,
)


class _FakeRedis:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._ttl: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._data[key] = value
        self._ttl[key] = ttl

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._ttl.pop(key, None)


def test_create_and_consume_bind_token():
    redis = _FakeRedis()
    user_id = uuid4()

    async def _run():
        token = await create_max_bind_token(redis, user_id)
        assert token
        assert redis._ttl[f"max_bind:{token}"] == BIND_TOKEN_TTL_SEC
        resolved = await consume_max_bind_token(redis, token)
        assert resolved == user_id
        again = await consume_max_bind_token(redis, token)
        assert again is None

    asyncio.run(_run())


def test_consume_unknown_token():
    redis = _FakeRedis()

    async def _run():
        assert await consume_max_bind_token(redis, "missing") is None

    asyncio.run(_run())
