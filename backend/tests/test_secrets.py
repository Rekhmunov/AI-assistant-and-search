from app.core.secrets import secrets_match


def test_secrets_match_equal():
    assert secrets_match("abc", "abc") is True


def test_secrets_match_different():
    assert secrets_match("abc", "abd") is False


def test_secrets_match_empty_expected():
    assert secrets_match("abc", "") is False
