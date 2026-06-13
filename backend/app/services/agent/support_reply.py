"""Ответы поддержки: vision + единый agent loop в MAX."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.models.user import User
from app.services.agent.content import build_dm_command_content
from app.services.agent.interaction import (
    interaction_mode,
    resolve_command_from_text,
    support_instructions,
)
from app.services.agent.knowledge import retrieve_knowledge_context
from app.services.agent.max_media import load_message_vision_images
from app.services.agent.profile import agent_config
from app.services.attachment_bundle import VisionImage
from app.services.bot import MaxBotService
from app.services.vision_service import VisionNotSupportedError, summarize_vision_for_search

logger = logging.getLogger(__name__)

_VISION_HINTS = (
    "картин",
    "фото",
    "изображ",
    "ocr",
    "распозна",
    "перевед",
    "текст с",
    "прочитай",
    "что на",
)


def _default_vision_query(text: str) -> str:
    low = (text or "").lower()
    if any(h in low for h in _VISION_HINTS) or "translate" in low:
        if "перевед" in low or "translate" in low:
            return "Распознай весь текст на изображении и переведи на русский. Сохрани структуру."
        return "Распознай и изложи весь текст с изображения на русском."
    return (text or "").strip() or "Опиши содержимое изображения и извлеки весь текст."


async def build_interactive_reply(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    *,
    text: str,
    payload: dict[str, Any] | None = None,
    message_id_value: str | None = None,
    vision_images: list[VisionImage] | None = None,
    bot: MaxBotService | None = None,
    force_command: bool = False,
    chat_id: int | None = None,
    author: str = "",
) -> tuple[str, list[dict]]:
    """Возвращает (text, attachments) для send_message."""
    cfg = agent_config(agent)
    mode = interaction_mode(cfg)
    command, args = resolve_command_from_text(text, cfg)
    configured_cmd = cfg.get("dm_command")

    use_command_pipeline = (
        force_command
        or (mode == "command" and command)
        or (mode == "both" and configured_cmd and command == str(configured_cmd).lower().split()[0])
    )

    if use_command_pipeline and command:
        from app.services.agent.content import DeliveryContent

        content: DeliveryContent = await build_dm_command_content(db, redis_client, user, agent, bot=bot)
        return content.text, content.attachments or []

    images = list(vision_images or [])
    if not images and payload:
        images = await load_message_vision_images(
            payload,
            bot=bot,
            message_id_value=message_id_value,
        )

    vision_note = ""
    if images:
        query = _default_vision_query(text)
        if args:
            query = f"{query}\n\nУточнение пользователя: {args}"
        try:
            vision_note = await summarize_vision_for_search(
                query,
                images,
                [],
                db=db,
                redis_client=redis_client,
            )
        except VisionNotSupportedError as exc:
            vision_note = str(exc)
        except Exception as exc:
            logger.warning("Agent vision failed: %s", exc)
            vision_note = "Не удалось обработать изображение. Попробуйте другое фото или позже."

    question = (text or "").strip()
    if not question and vision_note:
        question = "Обработай изображение согласно запросу пользователя."

    knowledge = await retrieve_knowledge_context(db, agent, question)
    instructions = support_instructions(agent, cfg)
    enriched_question = question
    if instructions:
        enriched_question = f"{question}\n\n[Инструкции владельца]\n{instructions[:2500]}"
    if knowledge:
        enriched_question = f"{enriched_question}\n\n[База знаний]\n{knowledge[:4000]}"

    from app.services.agent.agent_runtime import (
        run_max_interactive_loop,
        should_run_max_loop_background,
    )
    from app.services.agent.max_compliance import webhook_llm_allowed

    # Rate limit: предотвращает бесплатное потребление LLM через MAX webhook
    if not await webhook_llm_allowed(str(user.id)):
        return "Слишком много запросов. Попробуйте позже.", []

    if should_run_max_loop_background(question) and chat_id is not None:
        from app.workers.agent_tasks import enqueue_max_agent_loop_background

        enqueue_max_agent_loop_background(
            agent_id=str(agent.id),
            user_id=str(user.id),
            user_text=enriched_question,
            chat_id=chat_id,
            author=author,
            vision_context=vision_note,
        )
        return "Обрабатываю запрос, ответ пришлю в чат…", []

    loop_result = await run_max_interactive_loop(
        db,
        redis_client,
        user,
        agent,
        user_text=enriched_question,
        chat_id=chat_id,
        author=author,
        vision_context=vision_note,
        bot=bot,
    )
    reply_text = (loop_result.text or "").strip()
    if not reply_text and not loop_result.attachments:
        reply_text = "Готово."
    return reply_text, loop_result.attachments
