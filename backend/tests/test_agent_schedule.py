from datetime import datetime, timedelta, timezone

from app.services.agent.schedule import MSK, next_weekly_run, parse_reminder_schedule


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


def test_next_weekly_run_skips_past_today():
    now = datetime(2026, 6, 2, 11, 0, tzinfo=MSK)  # Monday 11:00
    run = next_weekly_run(0, 10, 0, now=now)
    assert run.weekday() == 0
    assert run > now
