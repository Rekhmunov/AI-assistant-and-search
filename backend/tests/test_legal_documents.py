"""Юридические документы — правила удаления версий."""

from app.services.legal_documents import CONSENT_BLOCKED_ERROR, ONLY_VERSION_ERROR, LegalVersionDeleteBlocked


def test_only_version_error_message():
    assert "единственную" in ONLY_VERSION_ERROR


def test_consent_blocked_error_message():
    assert "пользователь" in CONSENT_BLOCKED_ERROR


def test_legal_version_delete_blocked_carries_message():
    err = LegalVersionDeleteBlocked(CONSENT_BLOCKED_ERROR)
    assert err.args[0] == CONSENT_BLOCKED_ERROR


def test_reconsent_slugs_include_cookies():
    assert "cookies" in RECONSENT_SLUGS
    assert "privacy" in RECONSENT_SLUGS
