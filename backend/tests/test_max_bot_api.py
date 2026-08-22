"""MAX Bot API base URL и TLS для platform-api2."""

from app.core.config import Settings
from app.services.bot import _max_api_base, _max_ssl_verify, DEFAULT_MAX_BOT_API_BASE


def test_max_api_base_defaults_to_platform_api2():
    s = Settings(max_bot_api_base="")
    assert _max_api_base(s) == DEFAULT_MAX_BOT_API_BASE


def test_max_ssl_verify_prefers_max_ca_bundle():
    s = Settings(
        max_ca_bundle_file="/opt/aisearch/certs/russian_trusted_root_ca.pem",
        gigachat_ca_bundle_file="/other.pem",
    )
    assert _max_ssl_verify(s) == "/opt/aisearch/certs/russian_trusted_root_ca.pem"


def test_max_ssl_verify_falls_back_to_gigachat_bundle():
    s = Settings(
        max_ca_bundle_file="",
        gigachat_ca_bundle_file="/opt/aisearch/certs/russian_trusted_root_ca.pem",
    )
    assert _max_ssl_verify(s) == "/opt/aisearch/certs/russian_trusted_root_ca.pem"
