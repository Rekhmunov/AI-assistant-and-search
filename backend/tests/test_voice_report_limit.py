import asyncio

import pytest
from fastapi import HTTPException

from app.core.limiter import VOICE_REPORTS_PER_IP_PER_HOUR, RateLimiter


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key: str) -> int:
        self.store[key] = max(0, self.store.get(key, 0) - 1)
        return self.store[key]

    async def expire(self, key: str, sec: int) -> None:
        self.ttl[key] = sec


def test_voice_report_limit_blocks_after_threshold():
    limiter = RateLimiter(_FakeRedis())
    ip = "203.0.113.1"

    for _ in range(VOICE_REPORTS_PER_IP_PER_HOUR):
        asyncio.run(limiter.check_voice_report_limit(ip))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(limiter.check_voice_report_limit(ip))
    assert exc.value.status_code == 429
