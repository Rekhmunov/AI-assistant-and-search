"""Тесты статусов шагов агента."""

from __future__ import annotations

from app.services.agent.agent_status import (
    STATUS_ADMIN_CHECK,
    TOOL_STATUS_LABELS,
    tool_status_label,
)


def test_tool_status_label_known():
    assert tool_status_label("web_search") == TOOL_STATUS_LABELS["web_search"]
    assert "интернет" in tool_status_label("web_search").lower()


def test_tool_status_label_unknown():
    assert tool_status_label("unknown_tool") == "Выполняю проверку…"


def test_admin_check_status_human_readable():
    assert "администратор" in STATUS_ADMIN_CHECK.lower()
