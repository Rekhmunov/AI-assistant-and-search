"""Тесты парсинга команд в личке MAX."""

from __future__ import annotations

from app.services.agent.dm_commands import parse_dm_command


def test_parse_slash_command():
    cmd, args = parse_dm_command("/news сегодня")
    assert cmd == "news"
    assert args == "сегодня"


def test_parse_plain_command():
    cmd, args = parse_dm_command("картинка кот")
    assert cmd == "картинка"
    assert args == "кот"
