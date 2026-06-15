"""Разбор расписания напоминаний с учётом часового пояса пользователя."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MSK = timezone(timedelta(hours=3))
DEFAULT_TZ_NAME = "Europe/Moscow"

# Максимальное число переносов pending-напоминания при временных ошибках
MAX_REMINDER_DEFERS = 12  # 12 × 10 мин = 2 часа

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


def next_monthly_run(
    day: int,
    hour: int,
    minute: int,
    *,
    now: datetime | None = None,
    tz: timezone | None = None,
) -> datetime:
    """Следующий запуск в N-й день месяца в HH:MM (в часовом поясе пользователя)."""
    import calendar
    tz = tz or MSK
    now = now or datetime.now(tz)
    candidate = now.replace(day=min(day, calendar.monthrange(now.year, now.month)[1]),
                            hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        # Переходим к следующему месяцу
        if now.month == 12:
            year, month = now.year + 1, 1
        else:
            year, month = now.year, now.month + 1
        candidate = candidate.replace(
            year=year,
            month=month,
            day=min(day, calendar.monthrange(year, month)[1]),
        )
    return candidate


def parse_reminder_schedule(
    schedule_text: str,
    *,
    now: datetime | None = None,
    tz_name: str | None = None,
) -> tuple[datetime, str | None]:
    """
    Возвращает (run_at UTC, recurrence).
    recurrence: None | daily | weekly:<weekday> | monthly:<day>
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

    rel_hour = re.search(r"через\s+(\d+)\s*(?:час|часа|часов)", raw)
    if rel_hour:
        run = now_local + timedelta(hours=int(rel_hour.group(1)))
        return run.astimezone(timezone.utc), None

    if re.search(r"(?:раз\s+в\s+час|кажд\w+\s+час|every\s+hour|hourly)", raw):
        run = now_local + timedelta(hours=1)
        return run.astimezone(timezone.utc), "hourly"

    # Monthly: "каждое 20-е", "раз в месяц каждое 20", "20-го числа каждый месяц", "ежемесячно 20"
    monthly_m = re.search(
        r"(?:кажд\w+\s+месяц|раз\s+в\s+месяц|ежемесячно|кажд\w+\s+(\d{1,2})[-\w]*\s+числ|(\d{1,2})[-\w]*\s+числ\w*\s+каждый)",
        raw,
    )
    monthly_day_m = re.search(r"(\d{1,2})[-\w]*\s+(?:числ|го\b)", raw)
    if not monthly_day_m:
        monthly_day_m = re.search(r"каждое\s+(\d{1,2})", raw)
    if not monthly_day_m:
        monthly_day_m = re.search(r"(\d{1,2})-?е?\s+(?:числ|го)", raw)

    if re.search(r"(?:кажд\w+\s+месяц|раз\s+в\s+месяц|ежемесячно|кажд\w+\s+\d{1,2}[-\w]*\s*числ)", raw) and monthly_day_m:
        day = int(monthly_day_m.group(1))
        if 1 <= day <= 31:
            hm = _parse_time_hm(raw) or (9, 0)
            run = next_monthly_run(day, hm[0], hm[1], now=now_local, tz=user_tz)
            return run.astimezone(timezone.utc), f"monthly:{day}"

    if "послезавтра" in raw:
        hm = _parse_time_hm(raw) or (9, 0)
        run = (now_local + timedelta(days=2)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return run.astimezone(timezone.utc), None

    if "сегодня" in raw:
        hm = _parse_time_hm(raw)
        if hm:
            run = now_local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if run <= now_local:
                run += timedelta(minutes=2)
            return run.astimezone(timezone.utc), None
        if any(word in raw for word in ("сделай", "сделать", "отправ", "пришли", "запусти", "выполни")):
            run = now_local + timedelta(minutes=2)
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
        if re.search(rf"\b{re.escape(name)}\b", raw):
            hm = _parse_time_hm(raw) or (9, 0)
            run = next_weekly_run(wd, hm[0], hm[1], now=now_local, tz=user_tz)
            return run.astimezone(timezone.utc), f"weekly:{wd}"

    iso = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})", schedule_text)
    if iso:
        dt = datetime.fromisoformat(iso.group(1).replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=user_tz)
        return dt.astimezone(timezone.utc), None

    # Голое время HH:MM — теперь РАЗОВОЕ (не ежедневное)
    hm = _parse_time_hm(raw)
    if hm:
        run = now_local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if run <= now_local:
            run += timedelta(days=1)
        return run.astimezone(timezone.utc), None  # None = одноразовое

    raise ValueError("schedule_unparseable")


def normalize_schedule_phrase(text: str) -> str | None:
    """Приводит фразу расписания к виду, который понимает parse_reminder_schedule."""
    raw = (text or "").strip()
    if not raw:
        return None
    low = raw.lower()
    hm = _parse_time_hm(raw)
    time_part = f"{hm[0]}:{hm[1]:02d}" if hm else None

    if re.search(r"кажд\w+\s+день", low) or "ежедневно" in low:
        return f"каждый день в {time_part}" if time_part else "каждый день"

    # Monthly
    monthly_day_m = re.search(r"(\d{1,2})[-\w]*\s+(?:числ|го\b)", low)
    if not monthly_day_m:
        monthly_day_m = re.search(r"каждое\s+(\d{1,2})", low)
    if re.search(r"(?:кажд\w+\s+месяц|раз\s+в\s+месяц|ежемесячно)", low) and monthly_day_m:
        day = monthly_day_m.group(1)
        return f"раз в месяц каждое {day} число в {time_part}" if time_part else f"раз в месяц каждое {day} число"

    for name in _WEEKDAY_MAP:
        if re.search(rf"\b{re.escape(name)}\b", low):
            return f"каждый {name} в {time_part}" if time_part else f"каждый {name}"

    if "послезавтра" in low:
        return f"послезавтра в {time_part}" if time_part else "послезавтра"

    if "сегодня" in low:
        if time_part:
            return f"сегодня в {time_part}"
        if any(word in low for word in ("сделай", "сделать", "отправ", "пришли", "запусти", "выполни")):
            return "через 2 минуты"
        return None

    if "завтра" in low:
        return f"завтра в {time_part}" if time_part else "завтра"

    if re.search(r"через\s+\d+", low):
        return raw

    if re.search(r"(?:раз\s+в\s+час|кажд\w+\s+час|every\s+hour|hourly)", low):
        return "каждый час"

    # Голое время — одноразовое (не ежедневное)
    if time_part:
        return f"сегодня в {time_part}"

    return raw


def is_schedule_parseable(schedule_text: str, tz_name: str | None = None) -> bool:
    try:
        parse_reminder_schedule(schedule_text, tz_name=tz_name)
        return True
    except ValueError:
        return False


def format_run_at_local(run_at_utc: datetime, tz_name: str | None) -> str:
    tz = resolve_user_timezone(tz_name)
    local = run_at_utc.astimezone(tz)
    label = tz_name or DEFAULT_TZ_NAME
    return f"{local.strftime('%d.%m.%Y %H:%M')} ({label})"
