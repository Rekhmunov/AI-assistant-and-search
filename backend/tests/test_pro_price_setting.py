from app.core.config import Settings
from app.services.app_settings import SETTING_KEYS, default_for_key


def test_pro_price_rub_in_setting_keys():
    assert "pro_price_rub" in SETTING_KEYS
    assert SETTING_KEYS["pro_price_rub"] is int


def test_pro_price_default_from_env():
    settings = Settings(pro_price_rub=499)
    assert default_for_key("pro_price_rub", settings) == 499


def test_pro_price_default_is_299():
    settings = Settings()
    assert default_for_key("pro_price_rub", settings) == 299
