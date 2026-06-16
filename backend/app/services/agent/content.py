"""Сборка текста и вложений для отправки в MAX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder
from app.models.user import User
from app.services.agent.document_delivery import build_document_delivery_content
from app.services.agent.generate_content import generate_reminder_text
from app.services.agent.image_delivery import build_image_attachments
from app.services.agent.news_post_delivery import build_news_post_content
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

    if profile.content_pipeline == "web_digest_images":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        text, attachments = await build_news_post_content(
            db,
            redis_client,
            user,
            topic=topic,
            header=base_text if base_text != topic else "",
            min_chars=int(cfg.get("post_min_chars") or 500),
            max_chars=int(cfg.get("post_max_chars") or 1000),
            image_min=int(cfg.get("post_image_count_min") or 1),
            image_max=int(cfg.get("post_image_count_max") or 3),
            bot=bot,
        )
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "web_digest":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        raw_min = cfg.get("post_min_chars")
        raw_max = cfg.get("post_max_chars")
        min_chars = int(raw_min) if raw_min else None
        max_chars = int(raw_max) if raw_max else None
        text = await build_web_digest_text(
            db,
            redis_client,
            user,
            topic=topic,
            header=base_text if base_text != topic else "",
            min_chars=min_chars,
            max_chars=max_chars,
        )
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "image_gen":
        prompt = str(cfg.get("image_prompt") or base_text or "").strip()
        text, attachments, _ = await build_image_attachments(prompt, bot=bot)
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "document_gen":
        instruction = str(cfg.get("generation_prompt") or base_text or "").strip()
        output_format = str(cfg.get("output_format") or "docx").strip().lower()
        result = await build_document_delivery_content(
            db,
            redis_client,
            user,
            instruction,
            output_format=output_format,
            bot=bot,
        )
        return DeliveryContent(text=result.text, attachments=result.attachments)

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
    """Контент по команде в личке (dm_assistant). Поддерживает все content_pipeline."""
    profile = agent_profile(agent)
    cfg = agent_config(agent)
    base_text = str(cfg.get("reminder_message") or "")

    if profile.content_pipeline == "web_digest":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        raw_min = cfg.get("post_min_chars")
        raw_max = cfg.get("post_max_chars")
        text = await build_web_digest_text(
            db, redis_client, user,
            topic=topic,
            header="",
            min_chars=int(raw_min) if raw_min else None,
            max_chars=int(raw_max) if raw_max else None,
        )
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "web_digest_images":
        topic = str(cfg.get("search_topic") or base_text or "новости").strip()
        text, attachments = await build_news_post_content(
            db,
            redis_client,
            user,
            topic=topic,
            header="",
            min_chars=int(cfg.get("post_min_chars") or 300),
            max_chars=int(cfg.get("post_max_chars") or 800),
            image_min=int(cfg.get("post_image_count_min") or 1),
            image_max=int(cfg.get("post_image_count_max") or 2),
            bot=bot,
        )
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "image_gen":
        prompt = str(cfg.get("image_prompt") or base_text or "").strip()
        text, attachments, _ = await build_image_attachments(prompt, bot=bot)
        return DeliveryContent(text=text, attachments=attachments)

    if profile.content_pipeline == "document_gen":
        instruction = str(cfg.get("generation_prompt") or base_text or "").strip()
        output_format = str(cfg.get("output_format") or "docx").strip().lower()
        result = await build_document_delivery_content(
            db,
            redis_client,
            user,
            instruction,
            output_format=output_format,
            bot=bot,
        )
        return DeliveryContent(text=result.text, attachments=result.attachments)

    if profile.content_pipeline == "llm_generate":
        instruction = str(cfg.get("generation_prompt") or base_text or "").strip()
        from app.services.agent.generate_content import generate_reminder_text

        text = await generate_reminder_text(db, redis_client, user, instruction)
        return DeliveryContent(text=text, attachments=[])

    if profile.content_pipeline == "group_summary":
        return DeliveryContent(text=base_text or "Команда принята.", attachments=[])

    return DeliveryContent(text=base_text or "Готово.", attachments=[])
