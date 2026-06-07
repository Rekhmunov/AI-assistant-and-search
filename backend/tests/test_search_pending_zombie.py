from datetime import datetime, timedelta, timezone

from app.services.search_pending import is_pending_zombie, pending_active_seconds


def test_pending_active_seconds_from_started_at():
    started = (datetime.now(timezone.utc) - timedelta(seconds=80)).isoformat()
    assert pending_active_seconds({"started_at": started}) >= 79


def test_is_pending_zombie_when_too_old():
    started = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    assert is_pending_zombie({"started_at": started, "phase": "searching"}) is True


def test_is_pending_zombie_when_recent():
    started = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    assert is_pending_zombie({"started_at": started, "phase": "searching"}) is False
