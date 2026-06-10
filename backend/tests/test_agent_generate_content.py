"""Тесты генерации контента напоминаний."""

from __future__ import annotations

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock, patch

from app.models.agent import AgentRole
from app.services.agent.content import build_delivery_content
from app.services.agent.generate_content import wants_llm_generated_content
from app.services.agent.profile import agent_profile


def test_wants_llm_generated_poem():
    assert wants_llm_generated_content("Просто напиши стишок 4 строки")
    assert wants_llm_generated_content("напиши стихотворение про осень")
    assert wants_llm_generated_content("сгенерируй шутку")


def test_literal_reminder_not_generation():
    assert not wants_llm_generated_content("Напомни про встречу в 10")
    assert not wants_llm_generated_content("Встреча")
    assert not wants_llm_generated_content("Привет")


def test_profile_llm_generate_pipeline():
    agent = SimpleNamespace(
        role=AgentRole.PERSONAL_REMINDER.value,
        max_chat_id=None,
        config={"reminder_message": "напиши стишок на 4 строки"},
    )
    profile = agent_profile(agent)  # type: ignore[arg-type]
    assert profile.content_pipeline == "llm_generate"


def test_build_delivery_generates_instead_of_literal():
    agent = SimpleNamespace(
        role=AgentRole.PERSONAL_REMINDER.value,
        max_chat_id=None,
        config={
            "content_pipeline": "llm_generate",
            "generation_prompt": "напиши стишок на 4 строки",
            "reminder_message": "напиши стишок на 4 строки",
        },
    )
    user = SimpleNamespace(id="u1")
    reminder = SimpleNamespace(message_text="напиши стишок на 4 строки")

    async def _run():
        with patch(
            "app.services.agent.content.generate_reminder_text",
            new_callable=AsyncMock,
            return_value="Роза упала на лапу Азора.\nСолнце светит.\nДень идёт.\nВсё хорошо.",
        ):
            return await build_delivery_content(
                db=None,
                redis_client=None,
                user=user,
                agent=agent,
                reminder=reminder,
            )

    content = asyncio.run(_run())
    assert "стишок" not in content.text.lower()
    assert "Роза" in content.text or "Азора" in content.text
