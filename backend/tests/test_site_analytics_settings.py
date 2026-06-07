from app.services.app_settings import SETTING_KEYS, default_for_key


def test_yandex_metrica_counter_id_in_setting_keys():
    assert "yandex_metrica_counter_id" in SETTING_KEYS
    assert SETTING_KEYS["yandex_metrica_counter_id"] is str


def test_yandex_webmaster_verification_in_setting_keys():
    assert "yandex_webmaster_verification" in SETTING_KEYS
    assert SETTING_KEYS["yandex_webmaster_verification"] is str


def test_analytics_defaults_empty():
    assert default_for_key("yandex_metrica_counter_id") == ""
    assert default_for_key("yandex_webmaster_verification") == ""
