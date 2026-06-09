"""Разбор расписания напоминаний (MVP, Europe/Moscow)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

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


def _parse_time_hm(text: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*час", text, re.I)
    if m:
        return int(m.group(1)), 0
    return None


def next_weekly_run(weekday: int, hour: int, minute: int, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(MSK)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - target.weekday()) % 7
    if days_ahead == 0 and target <= now:
        days_ahead = 7
    return target + timedelta(days=days_ahead)


def parse_reminder_schedule(schedule_text: str, *, now: datetime | None = None) -> tuple[datetime, str | None]:
    """
    Возвращает (run_at UTC, recurrence).
    recurrence: None | weekly:<weekday>
    """
    now_msk = now or datetime.now(MSK)
    raw = (schedule_text or "").strip().lower()
    if not raw:
        raise ValueError("schedule_empty")

    if "завтра" in raw:
        hm = _parse_time_hm(raw) or (9, 0)
        run = (now_msk + timedelta(days=1)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return run.astimezone(timezone.utc), None

    for name, wd in _WEEKDAY_MAP.items():
        if name in raw:
            hm = _parse_time_hm(raw) or (9, 0)
            run = next_weekly_run(wd, hm[0], hm[1], now=now_msk)
            return run.astimezone(timezone.utc), f"weekly:{wd}"

    iso = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})", schedule_text)
    if iso:
        dt = datetime.fromisoformat(iso.group(1).replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MSK)
        return dt.astimezone(timezone.utc), None

    raise ValueError("schedule_unparseable")
