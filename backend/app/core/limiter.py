from datetime import datetime, timedelta, timezone

import redis.asyncio as redis

from app.core.config import Settings, get_settings
from app.models.user import Plan

MSK = timezone(timedelta(hours=3))


def _day_key(prefix: str, user_id: str) -> str:
    today = datetime.now(MSK).strftime("%Y-%m-%d")
    return f"{prefix}:{user_id}:{today}"


class RateLimiter:
    def __init__(self, redis_client: redis.Redis, settings: Settings | None = None):
        self.redis = redis_client
        self.settings = settings or get_settings()

    async def _search_limit_for_plan(self, plan: Plan) -> int:
        if plan == Plan.PRO:
            key = "setting:pro_searches_per_day"
            default = self.settings.pro_searches_per_day
        else:
            key = "setting:free_searches_per_day"
            default = self.settings.free_searches_per_day
        cached = await self.redis.get(key)
        if cached is not None:
            return int(cached)
        return default

    async def check_search_limit(self, user_id: str, plan: Plan) -> tuple[bool, int, int]:
        limit = await self._search_limit_for_plan(plan)
        key = _day_key("search", user_id)
        count = await self.redis.incr(key)
        if count == 1:
            now = datetime.now(MSK)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await self.redis.expireat(key, int(midnight.timestamp()))

        if count > limit:
            await self.redis.decr(key)
            return False, limit - max(0, count - 1), limit

        return True, count, limit

    async def release_search(self, user_id: str) -> None:
        key = _day_key("search", user_id)
        val = await self.redis.get(key)
        if val and int(val) > 0:
            await self.redis.decr(key)

    async def get_search_usage(self, user_id: str) -> int:
        key = _day_key("search", user_id)
        val = await self.redis.get(key)
        return int(val) if val else 0

    async def _global_yandex_limit(self) -> int:
        cached = await self.redis.get("setting:global_yandex_requests_per_day")
        if cached is not None:
            return int(cached)
        return self.settings.global_yandex_requests_per_day

    async def check_global_yandex_limit(self) -> bool:
        limit = await self._global_yandex_limit()
        key = _day_key("yandex_global", "all")
        count = await self.redis.incr(key)
        if count == 1:
            now = datetime.now(MSK)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await self.redis.expireat(key, int(midnight.timestamp()))
        if count > limit:
            await self.redis.decr(key)
            return False
        return True
