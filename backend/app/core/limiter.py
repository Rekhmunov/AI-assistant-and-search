from datetime import datetime, timedelta, timezone

import redis.asyncio as redis

from app.core.config import Settings, get_settings
from app.models.user import Plan, User

MSK = timezone(timedelta(hours=3))

GUEST_CREATIONS_PER_IP_PER_DAY = 20
VOICE_REPORTS_PER_IP_PER_HOUR = 60


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

    async def _guest_search_limit(self) -> int:
        cached = await self.redis.get("setting:guest_searches_per_day")
        if cached is not None:
            return int(cached)
        return self.settings.guest_searches_per_day

    async def _limit_for_user(self, user: User) -> int:
        if user.guest_key and not user.email:
            return await self._guest_search_limit()
        return await self._search_limit_for_plan(user.plan)

    def _is_guest_user(self, user: User | None) -> bool:
        return user is not None and bool(user.guest_key) and not user.email

    def _guest_search_key(self, user_id: str) -> str:
        return f"search_guest:{user_id}"

    async def check_voice_report_limit(self, client_ip: str) -> None:
        from fastapi import HTTPException, status

        key = f"voice_report:{client_ip}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 3600)
        if count > VOICE_REPORTS_PER_IP_PER_HOUR:
            await self.redis.decr(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много диагностических запросов. Попробуйте позже.",
            )

    async def check_guest_creation_limit(self, client_ip: str) -> None:
        from fastapi import HTTPException, status

        key = _day_key("guest_create", client_ip)
        count = await self.redis.incr(key)
        if count == 1:
            now = datetime.now(MSK)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await self.redis.expireat(key, int(midnight.timestamp()))
        if count > GUEST_CREATIONS_PER_IP_PER_DAY:
            await self.redis.decr(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много гостевых сессий с этого адреса. Попробуйте позже или войдите.",
            )

    async def _check_guest_ip_search_limit(self, client_ip: str, limit: int) -> tuple[bool, int, int]:
        key = f"guest_ip_search_lifetime:{client_ip}"
        count = await self.redis.incr(key)
        if count > limit:
            await self.redis.decr(key)
            return False, max(0, limit), limit
        return True, count, limit

    async def check_search_limit(
        self,
        user_id: str,
        plan: Plan,
        user: User | None = None,
        *,
        client_ip: str | None = None,
    ) -> tuple[bool, int, int]:
        if user is not None:
            limit = await self._limit_for_user(user)
        else:
            limit = await self._search_limit_for_plan(plan)

        if self._is_guest_user(user):
            key = self._guest_search_key(user_id)
            count = await self.redis.incr(key)
            if count > limit:
                await self.redis.decr(key)
                return False, max(0, count - 1), limit

            if client_ip:
                ip_ok, ip_used, ip_limit = await self._check_guest_ip_search_limit(client_ip, limit)
                if not ip_ok:
                    await self.redis.decr(key)
                    return False, ip_used, ip_limit

            return True, count, limit

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

    async def release_search(self, user_id: str, user: User | None = None) -> None:
        if self._is_guest_user(user):
            key = self._guest_search_key(user_id)
        else:
            key = _day_key("search", user_id)
        val = await self.redis.get(key)
        if val and int(val) > 0:
            await self.redis.decr(key)

    async def get_search_usage(self, user_id: str, user: User | None = None) -> int:
        if self._is_guest_user(user):
            key = self._guest_search_key(user_id)
        else:
            key = _day_key("search", user_id)
        val = await self.redis.get(key)
        return int(val) if val else 0

    async def usage_and_limit(self, user: User) -> tuple[int, int]:
        used = await self.get_search_usage(str(user.id), user)
        limit = await self._limit_for_user(user)
        return used, limit

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

    async def _image_gen_limit_for_plan(self, plan: Plan) -> int:
        if plan != Plan.PRO:
            return 0
        cached = await self.redis.get("setting:pro_image_gens_per_day")
        if cached is not None:
            return int(cached)
        return self.settings.pro_image_gens_per_day

    async def check_image_gen_limit(self, user_id: str, plan: Plan) -> tuple[bool, int, int]:
        limit = await self._image_gen_limit_for_plan(plan)
        if limit <= 0:
            return False, 0, 0
        key = _day_key("image_gen", user_id)
        count = await self.redis.incr(key)
        if count == 1:
            now = datetime.now(MSK)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await self.redis.expireat(key, int(midnight.timestamp()))
        if count > limit:
            await self.redis.decr(key)
            return False, max(0, count - 1), limit
        return True, count, limit

    async def release_image_gen(self, user_id: str) -> None:
        key = _day_key("image_gen", user_id)
        val = await self.redis.get(key)
        if val and int(val) > 0:
            await self.redis.decr(key)

    async def get_image_gen_usage(self, user_id: str) -> int:
        key = _day_key("image_gen", user_id)
        val = await self.redis.get(key)
        return int(val) if val else 0

    async def _free_doc_gen_limit(self) -> int:
        cached = await self.redis.get("setting:free_doc_gens_per_day")
        if cached is not None:
            return int(cached)
        return self.settings.free_doc_gens_per_day

    async def _pro_doc_gen_limit(self) -> int:
        cached = await self.redis.get("setting:pro_doc_gens_per_day")
        if cached is not None:
            return int(cached)
        return self.settings.pro_doc_gens_per_day

    async def _guest_doc_gen_lifetime_limit(self) -> int:
        cached = await self.redis.get("setting:guest_doc_gens_lifetime")
        if cached is not None:
            return int(cached)
        return self.settings.guest_doc_gens_lifetime

    async def get_doc_gen_usage(self, user_id: str, user: User) -> tuple[int, int]:
        """(used, limit) — без инкремента."""
        if user.guest_key and not user.email:
            key = f"doc_gen_guest:{user_id}"
            val = await self.redis.get(key)
            used = int(val) if val else 0
            limit = await self._guest_doc_gen_lifetime_limit()
            return used, limit
        if user.plan == Plan.PRO:
            key = _day_key("doc_gen", user_id)
            val = await self.redis.get(key)
            used = int(val) if val else 0
            limit = await self._pro_doc_gen_limit()
            return used, limit
        key = _day_key("doc_gen", user_id)
        val = await self.redis.get(key)
        used = int(val) if val else 0
        limit = await self._free_doc_gen_limit()
        return used, limit

    async def check_doc_gen_allowed(self, user_id: str, user: User) -> tuple[bool, int, int]:
        used, limit = await self.get_doc_gen_usage(user_id, user)
        if limit <= 0:
            return False, used, limit
        return used < limit, used, limit

    async def record_doc_gen_success(self, user_id: str, user: User) -> None:
        if user.guest_key and not user.email:
            key = f"doc_gen_guest:{user_id}"
            await self.redis.incr(key)
            return
        key = _day_key("doc_gen", user_id)
        count = await self.redis.incr(key)
        if count == 1:
            now = datetime.now(MSK)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await self.redis.expireat(key, int(midnight.timestamp()))
