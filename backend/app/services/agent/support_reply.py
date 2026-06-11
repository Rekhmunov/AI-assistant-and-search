"""Ответы поддержки: vision (OCR/перевод), база знаний, инструкции из треда."""

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


async def _answer_with_llm(
    db: AsyncSession,
    redis_client,
    user: User,
    *,
    question: str,
    instructions: str,
    knowledge: str,
    vision_note: str = "",
) -> str:
    from app.services.providers.factory import resolve_runtime_providers

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    system_parts = [
        "Ты — помощник в мессенджере MAX. Отвечай кратко и по делу на русском.",
    ]
    if instructions:
        system_parts.append(f"Инструкции владельца агента:\n{instructions[:3000]}")
    if knowledge:
        system_parts.append(f"База знаний (используй при ответе, не выдумывай):\n{knowledge[:6000]}")
    if vision_note:
        system_parts.append(f"Результат анализа изображения:\n{vision_note[:4000]}")

    user_text = question.strip() or "Помоги пользователю."
    try:
        if hasattr(llm, "complete_text"):
            return (
                await llm.complete_text(  # type: ignore[attr-defined]
                    [
                        {"role": "system", "text": "\n\n".join(system_parts)},
                        {"role": "user", "text": user_text[:2000]},
                    ],
                    model="pro",
                    max_tokens=900,
                    temperature=0.3,
                )
            ).strip()
    except Exception as exc:
        logger.warning("Support LLM failed: %s", exc)
    if vision_note:
        return vision_note[:3500]
    if knowledge:
        return "Нашёл информацию в базе знаний, но не удалось сформулировать ответ. Попробуйте переформулировать вопрос."
    return "Сейчас не могу ответить. Попробуйте позже."


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

    instructions = support_instructions(agent, cfg)
    knowledge = await retrieve_knowledge_context(db, agent, text)

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

    from app.services.agent.document_delivery import try_build_file_reply
    from app.services.agent.expense_tracker import handle_expense_tracker_reply

    expense_reply = await handle_expense_tracker_reply(
        db,
        redis_client,
        user,
        agent,
        question,
        bot=bot,
        chat_id=chat_id,
        author=author,
    )
    if expense_reply is not None:
        return expense_reply.text, expense_reply.attachments

    file_reply = await try_build_file_reply(
        db,
        redis_client,
        user,
        question,
        output_format=str(cfg.get("output_format") or "") or None,
        bot=bot,
    )
    if file_reply and file_reply.attachments:
        return file_reply.text, file_reply.attachments

    answer = await _answer_with_llm(
        db,
        redis_client,
        user,
        question=question,
        instructions=instructions,
        knowledge=knowledge,
        vision_note=vision_note,
    )
    return answer, []
