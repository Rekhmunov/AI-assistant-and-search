from unittest.mock import MagicMock

from app.core.auth_cookies import is_cross_site_cookie_context, refresh_cookie_kwargs


def _request(origin: str, host: str) -> MagicMock:
    req = MagicMock()
    req.headers = {"origin": origin}
    req.url.hostname = host
    return req


def test_same_origin_uses_lax_samesite():
    settings = MagicMock(debug=False, cookie_domain=".glosix.ru", refresh_token_expire_days=30)
    assert is_cross_site_cookie_context(_request("https://glosix.ru", "glosix.ru"), settings) is False
    kwargs = refresh_cookie_kwargs("token-value", settings=settings, request=_request("https://glosix.ru", "glosix.ru"))
    assert kwargs["samesite"] == "lax"


def test_cross_subdomain_uses_none_samesite():
    settings = MagicMock(debug=False, cookie_domain=".glosix.ru", refresh_token_expire_days=30)
    assert (
        is_cross_site_cookie_context(_request("https://glosix.ru", "api.glosix.ru"), settings) is True
    )
    kwargs = refresh_cookie_kwargs(
        "token-value",
        settings=settings,
        request=_request("https://glosix.ru", "api.glosix.ru"),
    )
    assert kwargs["samesite"] == "none"
    assert kwargs["secure"] is True
