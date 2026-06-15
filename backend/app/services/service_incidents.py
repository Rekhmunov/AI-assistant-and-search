"""Учёт сбоев внешних сервисов (Redis) для админ-дашборда."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Дебаунс: не отправлять email чаще чем раз в N секунд для одного сервиса
_NOTIFY_DEBOUNCE_SEC = 300  # 5 минут

_PREFIX = "svcinc:v1:"
_RECENT_KEY = f"{_PREFIX}recent"
_RECENT_MAX = 200
_DAY_TTL_SEC = 8 * 86400

SERVICE_LABELS: dict[str, str] = {
    "search": "Yandex Search",
    "glosix_search": "Поиск Glosix",
    "image_search": "Поиск картинок",
    "image_gen": "GigaChat (картинки)",
    "gpt": "LLM (ответ)",
    "perplexity": "Perplexity",
}


@dataclass(frozen=True)
class ServiceIncident:
    service: str
    kind: str
    message: str
    status_code: int | None = None
    at: datetime | None = None


def _day_key(service: str, day: str) -> str:
    return f"{_PREFIX}count:{service}:{day}"


def _day_str(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


async def _notify_admins_incident(
    redis_client: redis.Redis,
    service: str,
    kind: str,
    message: str,
    status_code: int | None,
) -> None:
    """Отправляет email-оповещение о сбое администраторам (с дебаунсом 5 мин)."""
    debounce_key = f"{_PREFIX}notified:{service}"
    try:
        acquired = await redis_client.set(debounce_key, "1", nx=True, ex=_NOTIFY_DEBOUNCE_SEC)
        if not acquired:
            return  # Уже отправляли недавно

        label = SERVICE_LABELS.get(service, service)
        status_hint = f" (HTTP {status_code})" if status_code else ""
        body = (
            f"Сбой сервиса: {label}{status_hint}\n"
            f"Тип: {kind}\n"
            f"{(message or '')[:300]}"
        )
        from app.services.email_notify import send_admin_alert
        subject = f"[Glosix] Сбой: {label}{status_hint}"
        await send_admin_alert(subject, body)
    except Exception:
        logger.exception("_notify_admins_incident failed")


async def record_service_incident(
    redis_client: redis.Redis | None,
    *,
    service: str,
    kind: str,
    message: str,
    status_code: int | None = None,
) -> None:
    if redis_client is None:
        return
    now = datetime.now(timezone.utc)
    payload = {
        "service": service,
        "kind": kind,
        "message": (message or "")[:500],
        "status_code": status_code,
        "at": now.isoformat(),
    }
    try:
        pipe = redis_client.pipeline()
        pipe.incr(_day_key(service, _day_str(now)))
        pipe.expire(_day_key(service, _day_str(now)), _DAY_TTL_SEC)
        pipe.lpush(_RECENT_KEY, json.dumps(payload, ensure_ascii=False))
        pipe.ltrim(_RECENT_KEY, 0, _RECENT_MAX - 1)
        await pipe.execute()
    except Exception:
        logger.exception("record_service_incident failed")

    # Email-оповещение (с дебаунсом 5 мин, не блокирует основной поток)
    try:
        await _notify_admins_incident(redis_client, service, kind, message, status_code)
    except Exception:
        logger.exception("incident admin notify failed")


async def _sum_counts(
    redis_client: redis.Redis,
    service: str,
    days: int,
) -> int:
    now = datetime.now(timezone.utc)
    total = 0
    for i in range(days):
        day = _day_str(now - timedelta(days=i))
        raw = await redis_client.get(_day_key(service, day))
        if raw:
            try:
                total += int(raw)
            except ValueError:
                pass
    return total


async def get_incidents_dashboard(
    redis_client: redis.Redis | None,
    *,
    recent_limit: int = 40,
) -> dict:
    if redis_client is None:
        return {"totals_24h": 0, "by_service": [], "recent": []}

    try:
        recent_raw = await redis_client.lrange(_RECENT_KEY, 0, max(0, recent_limit - 1))
    except Exception:
        logger.exception("get_incidents_dashboard lrange failed")
        recent_raw = []

    services_seen: set[str] = set()
    recent: list[dict] = []
    for item in recent_raw:
        try:
            data = json.loads(item)
        except (json.JSONDecodeError, TypeError):
            continue
        svc = str(data.get("service") or "unknown")
        services_seen.add(svc)
        recent.append(
            {
                "service": svc,
                "service_label": SERVICE_LABELS.get(svc, svc),
                "kind": str(data.get("kind") or ""),
                "message": str(data.get("message") or ""),
                "status_code": data.get("status_code"),
                "at": data.get("at"),
            }
        )

    for item in recent:
        services_seen.add(item["service"])

    by_service: list[dict] = []
    for svc in sorted(services_seen):
        by_service.append(
            {
                "service": svc,
                "service_label": SERVICE_LABELS.get(svc, svc),
                "count_24h": await _sum_counts(redis_client, svc, 1),
                "count_7d": await _sum_counts(redis_client, svc, 7),
                "last_message": next(
                    (r["message"] for r in recent if r["service"] == svc),
                    None,
                ),
                "last_at": next((r["at"] for r in recent if r["service"] == svc), None),
            }
        )
    by_service.sort(key=lambda x: (-x["count_24h"], -x["count_7d"]))

    totals_24h = sum(x["count_24h"] for x in by_service)
    return {"totals_24h": totals_24h, "by_service": by_service, "recent": recent}


# Поиск: деградация до ответа LLM без источников. Остальное — по-прежнему ошибка пользователю.
DEGRADABLE_SEARCH_SERVICES = frozenset({"search", "image_search"})
