from datetime import datetime, timedelta, timezone

from app.services.file_share_token import share_token_ttl_seconds_for_expires_at


def test_share_token_ttl_uses_remaining_file_lifetime():
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    ttl = share_token_ttl_seconds_for_expires_at(expires)
    assert 7000 < ttl <= 7200


def test_share_token_ttl_minimum_one_minute():
    expires = datetime.now(timezone.utc) + timedelta(seconds=10)
    ttl = share_token_ttl_seconds_for_expires_at(expires)
    assert ttl == 60
