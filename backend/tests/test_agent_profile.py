"""Тесты профиля и ролей агента."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.agent import AgentRole
from app.services.agent.profile import (
    SCHEDULED_ROLES,
    agent_profile,
    normalize_dm_command,
)


def test_scheduled_roles_include_news_and_image():
    assert AgentRole.NEWS_DIGEST.value in SCHEDULED_ROLES
    assert AgentRole.IMAGE_POST.value in SCHEDULED_ROLES
    assert AgentRole.DM_ASSISTANT.value not in SCHEDULED_ROLES


def test_news_digest_group_delivery():
    agent = SimpleNamespace(
        role=AgentRole.NEWS_DIGEST.value,
        max_chat_id=-123,
        config={"delivery_mode": "group", "search_topic": "AI"},
    )
    profile = agent_profile(agent)  # type: ignore[arg-type]
    assert profile.delivery_mode == "group"
    assert profile.content_pipeline == "web_digest"
    assert profile.needs_group is True


def test_dm_assistant_profile():
    agent = SimpleNamespace(
        role=AgentRole.DM_ASSISTANT.value,
        max_chat_id=None,
        config={"dm_command": "/news", "search_topic": "технологии"},
    )
    profile = agent_profile(agent)  # type: ignore[arg-type]
    assert profile.listens_dm_commands is True
    assert profile.content_pipeline == "web_digest"
    assert normalize_dm_command("news") == "news"
