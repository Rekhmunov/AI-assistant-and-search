"""Маршрут верификации Яндекс.Вебмастера."""

from pathlib import Path


def test_site_router_registered_in_main():
    src = Path(__file__).resolve().parents[1] / "app/main.py"
    text = src.read_text(encoding="utf-8")
    assert "site_router" in text
    assert "app.include_router(site_router)" in text


def test_nginx_template_proxies_yandex_verification():
    tpl = Path(__file__).resolve().parents[2] / "nginx/nginx.prod.conf.template"
    text = tpl.read_text(encoding="utf-8")
    assert "yandex_[a-f0-9]" in text


def test_webmaster_html_template():
    src = Path(__file__).resolve().parents[1] / "app/api/site.py"
    text = src.read_text(encoding="utf-8")
    assert "Verification: {code}" in text
    assert '/yandex_{code}.html' in text
