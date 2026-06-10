from datetime import datetime, timedelta, timezone

from app.services.agent.schedule import (
    MSK,
    is_schedule_parseable,
    next_weekly_run,
    normalize_schedule_phrase,
    parse_reminder_schedule,
    resolve_user_timezone,
)


def test_parse_tomorrow():
    now = datetime(2026, 6, 3, 12, 0, tzinfo=MSK)
    run_at, recurrence = parse_reminder_schedule("завтра в 9:00", now=now)
    assert recurrence is None
    local = run_at.astimezone(MSK)
    assert local.day == 4
    assert local.hour == 9
    assert local.minute == 0


def test_parse_weekly():
    now = datetime(2026, 6, 3, 12, 0, tzinfo=MSK)  # Tuesday
    run_at, recurrence = parse_reminder_schedule("каждый понедельник в 10:30", now=now)
    assert recurrence == "weekly:0"
    local = run_at.astimezone(MSK)
    assert local.weekday() == 0
    assert local.hour == 10
    assert local.minute == 30


def test_parse_in_minutes():
    now = datetime(2026, 6, 3, 12, 0, tzinfo=MSK)
    run_at, recurrence = parse_reminder_schedule("через 15 минут", now=now)
    assert recurrence is None
    delta = run_at.astimezone(MSK) - now
    assert 14 <= delta.total_seconds() / 60 <= 16


def test_timezone_utc_plus5():
    tz = resolve_user_timezone("UTC+5")
    now = datetime(2026, 6, 3, 12, 0, tzinfo=tz)
    run_at, _ = parse_reminder_schedule("завтра в 10:00", now=now, tz_name="UTC+5")
    local = run_at.astimezone(tz)
    assert local.hour == 10


def test_normalize_daily_with_time():
    assert normalize_schedule_phrase("каждый день в 16:35") == "каждый день в 16:35"
    assert normalize_schedule_phrase("каждый день") == "каждый день"


def test_normalize_rejects_bare_today():
    assert normalize_schedule_phrase("сегодня") is None
    assert normalize_schedule_phrase("сегодня в 16:35") == "сегодня в 16:35"


def test_is_schedule_parseable():
    assert is_schedule_parseable("каждый день в 16:35")
    assert not is_schedule_parseable("сегодня")


def test_parse_bare_time_daily():
    now = datetime(2026, 6, 3, 12, 0, tzinfo=MSK)
    run_at, recurrence = parse_reminder_schedule("16:10", now=now)
    assert recurrence == "daily"
    local = run_at.astimezone(MSK)
    assert local.hour == 16
    assert local.minute == 10


def test_next_weekly_run_skips_past_today():
    now = datetime(2026, 6, 2, 11, 0, tzinfo=MSK)  # Monday 11:00
    run = next_weekly_run(0, 10, 0, now=now)
    assert run.weekday() == 0
    assert run > now
