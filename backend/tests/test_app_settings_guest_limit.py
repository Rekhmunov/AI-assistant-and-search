from app.core.config import Settings
from app.services.app_settings import SETTING_KEYS, default_for_key


def test_guest_searches_per_day_in_setting_keys():
    assert "guest_searches_per_day" in SETTING_KEYS
    assert SETTING_KEYS["guest_searches_per_day"] is int


def test_guest_searches_default_from_env():
    settings = Settings(guest_searches_per_day=7)
    assert default_for_key("guest_searches_per_day", settings) == 7
