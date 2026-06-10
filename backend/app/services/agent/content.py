"""Сборка текста и вложений для отправки в MAX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder
from app.models.user import User
from app.services.agent.generate_content import generate_reminder_text
from app.services.agent.image_delivery import build_image_attachments
from app.services.agent.profile import agent_config, agent_profile
from app.services.agent.summarize import summarize_group_buffer
from app.services.agent.web_digest import build_web_digest_text
from app.services.bot import MaxBotService


@dataclass
class DeliveryContent:
    text: str
    attachments: list[dict]


async def build_delivery_content(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    reminder: AgentReminder | None,
    *,
    bot: MaxBotService | None = None,
) -> DeliveryContent:
    profile = agent_profile(agent)
    cfg = agent_config(agent)
    base_text = str(reminder.message_text if reminder else cfg.get("reminder_message") or "")

    if profile.content_pipeline == "group_summary":
        buffer = list(cfg.get("message_buffer") or [])
        text = await summarize_group_buffer(
            db,
            redis_client,
            user,
            buffer,
            header=base_text,
        )
        cfg["message_buffer"] = []
        agent.config = cfg
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "web_digest":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        text = await build_web_digest_text(
            db,
            redis_client,
            user,
            topic=topic,
            header=base_text if base_text != topic else "",
        )
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "image_gen":
        prompt = str(cfg.get("image_prompt") or base_text or "").strip()
        text, attachments = await build_image_attachments(prompt, bot=bot)
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "llm_generate":
        instruction = str(cfg.get("generation_prompt") or base_text or "").strip()
        text = await generate_reminder_text(db, redis_client, user, instruction)
        return DeliveryContent(text=text, attachments=[])

    return DeliveryContent(text=base_text or "—", attachments=[])


async def build_dm_command_content(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    *,
    bot: MaxBotService | None = None,
) -> DeliveryContent:
    """Контент по команде в личке (dm_assistant)."""
    profile = agent_profile(agent)
    cfg = agent_config(agent)
    base_text = str(cfg.get("reminder_message") or "")

    if profile.content_pipeline == "web_digest":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        text = await build_web_digest_text(db, redis_client, user, topic=topic, header="")
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "image_gen":
        prompt = str(cfg.get("image_prompt") or base_text or "").strip()
        text, attachments = await build_image_attachments(prompt, bot=bot)
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "group_summary":
        return DeliveryContent(text=base_text or "Команда принята.", attachments=[])

    return DeliveryContent(text=base_text or "Готово.", attachments=[])
