"""Admin settings API — нет конфликта имён с get_settings."""

from pathlib import Path


def test_update_settings_source_uses_app_config():
    path = Path(__file__).resolve().parents[1] / "app/api/admin/settings.py"
    src = path.read_text(encoding="utf-8")
    assert "app_config.get_settings()" in src
    assert "get_settings().anthropic" not in src
    assert "get_settings().deepseek" not in src
