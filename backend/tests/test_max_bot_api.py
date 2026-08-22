"""MAX Bot API base URL и TLS для platform-api2."""

from pathlib import Path

from app.core.config import Settings
from app.services.bot import (
    DEFAULT_MAX_CA_BUNDLE_PATHS,
    _max_api_base,
    _max_ssl_verify,
    DEFAULT_MAX_BOT_API_BASE,
)


def test_max_api_base_defaults_to_platform_api2():
    s = Settings(max_bot_api_base="")
    assert _max_api_base(s) == DEFAULT_MAX_BOT_API_BASE


def test_max_ssl_verify_prefers_max_ca_bundle(tmp_path):
    max_cert = tmp_path / "max.pem"
    other = tmp_path / "other.pem"
    max_cert.write_text("-----BEGIN CERTIFICATE-----\nmax\n-----END CERTIFICATE-----\n")
    other.write_text("-----BEGIN CERTIFICATE-----\nother\n-----END CERTIFICATE-----\n")
    s = Settings(
        max_ca_bundle_file=str(max_cert),
        gigachat_ca_bundle_file=str(other),
    )
    assert _max_ssl_verify(s) == str(max_cert)


def test_max_ssl_verify_falls_back_to_gigachat_bundle(tmp_path):
    gigachat_cert = tmp_path / "gigachat.pem"
    gigachat_cert.write_text("-----BEGIN CERTIFICATE-----\ngigachat\n-----END CERTIFICATE-----\n")
    s = Settings(
        max_ca_bundle_file="",
        gigachat_ca_bundle_file=str(gigachat_cert),
    )
    assert _max_ssl_verify(s) == str(gigachat_cert)


def test_max_ssl_verify_uses_bundled_cert_when_env_unset(tmp_path, monkeypatch):
    cert = tmp_path / "russian_trusted_root_ca.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")
    monkeypatch.setattr(
        "app.services.bot.DEFAULT_MAX_CA_BUNDLE_PATHS",
        (str(cert),),
    )
    s = Settings(max_ca_bundle_file="", gigachat_ca_bundle_file="")
    assert _max_ssl_verify(s) == str(cert)


def test_bundled_max_ca_cert_exists_in_repo():
    repo_cert = Path(__file__).resolve().parents[1] / "certs" / "russian_trusted_root_ca.pem"
    assert repo_cert.is_file()
    assert "BEGIN CERTIFICATE" in repo_cert.read_text(encoding="ascii")
    assert any(p.endswith("russian_trusted_root_ca.pem") for p in DEFAULT_MAX_CA_BUNDLE_PATHS)
