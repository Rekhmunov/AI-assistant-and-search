"""Тесты модерации группы."""

from __future__ import annotations

from app.services.agent.moderation import message_violates_rules


def test_stop_word_violation():
    rules = {"stop_words": ["спам"], "block_links": False}
    ok, reason = message_violates_rules("Это спам сообщение", rules)
    assert ok is True
    assert "спам" in reason


def test_link_violation():
    rules = {"stop_words": [], "block_links": True}
    ok, reason = message_violates_rules("Смотри https://evil.com", rules)
    assert ok is True
    assert "ссылка" in reason


def test_clean_message():
    rules = {"stop_words": ["спам"], "block_links": True}
    ok, _ = message_violates_rules("Обычное сообщение без проблем", rules)
    assert ok is False
