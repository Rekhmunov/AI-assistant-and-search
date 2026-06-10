"""Разбор расписания напоминаний с учётом часового пояса пользователя."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MSK = timezone(timedelta(hours=3))
DEFAULT_TZ_NAME = "Europe/Moscow"

_WEEKDAY_MAP = {
    "понедельник": 0,
    "пн": 0,
    "вторник": 1,
    "вт": 1,
    "среда": 2,
    "ср": 2,
    "четверг": 3,
    "чт": 3,
    "пятница": 4,
    "пт": 4,
    "суббота": 5,
    "сб": 5,
    "воскресенье": 6,
    "вс": 6,
}


def resolve_user_timezone(tz_name: str | None) -> timezone:
    raw = (tz_name or DEFAULT_TZ_NAME).strip()
    if not raw:
        return MSK
    upper = raw.upper().replace(" ", "")
    m = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", upper)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return MSK


def _parse_time_hm(text: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*час", text, re.I)
    if m:
        return int(m.group(1)), 0
    return None


def next_weekly_run(
    weekday: int,
    hour: int,
    minute: int,
    *,
    now: datetime | None = None,
    tz: timezone | None = None,
) -> datetime:
    tz = tz or MSK
    now = now or datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - target.weekday()) % 7
    if days_ahead == 0 and target <= now:
        days_ahead = 7
    return target + timedelta(days=days_ahead)


def parse_reminder_schedule(
    schedule_text: str,
    *,
    now: datetime | None = None,
    tz_name: str | None = None,
) -> tuple[datetime, str | None]:
    """
    Возвращает (run_at UTC, recurrence).
    recurrence: None | daily | weekly:<weekday>
    """
    user_tz = resolve_user_timezone(tz_name)
    now_local = now or datetime.now(user_tz)
    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=user_tz)
    else:
        now_local = now_local.astimezone(user_tz)

    raw = (schedule_text or "").strip().lower()
    if not raw:
        raise ValueError("schedule_empty")

    rel_min = re.search(r"через\s+(\d+)\s*(?:мин|минут)", raw)
    if rel_min:
        run = now_local + timedelta(minutes=int(rel_min.group(1)))
        return run.astimezone(timezone.utc), None

    if "сегодня" in raw:
        hm = _parse_time_hm(raw)
        if hm:
            run = now_local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if run <= now_local:
                run += timedelta(minutes=2)
            return run.astimezone(timezone.utc), None

    if "завтра" in raw:
        hm = _parse_time_hm(raw) or (9, 0)
        run = (now_local + timedelta(days=1)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return run.astimezone(timezone.utc), None

    if "каждый день" in raw or "ежедневно" in raw:
        hm = _parse_time_hm(raw) or (9, 0)
        run = now_local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if run <= now_local:
            run += timedelta(days=1)
        return run.astimezone(timezone.utc), "daily"

    for name, wd in _WEEKDAY_MAP.items():
        if name in raw:
            hm = _parse_time_hm(raw) or (9, 0)
            run = next_weekly_run(wd, hm[0], hm[1], now=now_local, tz=user_tz)
            return run.astimezone(timezone.utc), f"weekly:{wd}"

    iso = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})", schedule_text)
    if iso:
        dt = datetime.fromisoformat(iso.group(1).replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=user_tz)
        return dt.astimezone(timezone.utc), None

    raise ValueError("schedule_unparseable")


def format_run_at_local(run_at_utc: datetime, tz_name: str | None) -> str:
    tz = resolve_user_timezone(tz_name)
    local = run_at_utc.astimezone(tz)
    label = tz_name or DEFAULT_TZ_NAME
    return f"{local.strftime('%d.%m.%Y %H:%M')} ({label})"
