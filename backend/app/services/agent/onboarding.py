"""Валидация и итоги активации агента."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.services.agent.constants import CANCEL_PHRASES, SUPPORTED_ROLE_LABELS
from app.services.agent.profile import (
    EVENT_DRIVEN_ROLES,
    GROUP_ROLES,
    SCHEDULED_ROLES,
    agent_profile,
    normalize_dm_command,
)
from app.services.agent.schedule import parse_reminder_schedule


def user_wants_cancel(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(phrase in low for phrase in CANCEL_PHRASES)


def _config(agent: AgentInstance) -> dict[str, Any]:
    raw = agent.config
    return dict(raw) if isinstance(raw, dict) else {}


def validate_activation(agent: AgentInstance) -> None:
    cfg = _config(agent)
    role = agent.role
    if not role:
        raise ValueError("role_missing")

    profile = agent_profile(agent)

    if role in SCHEDULED_ROLES:
        if not cfg.get("schedule_text"):
            raise ValueError("schedule_missing")
        parse_reminder_schedule(
            str(cfg["schedule_text"]),
            tz_name=str(cfg.get("timezone") or "Europe/Moscow"),
        )

    if role == AgentRole.NEWS_DIGEST.value:
        if not (cfg.get("search_topic") or cfg.get("reminder_message")):
            raise ValueError("search_topic_missing")

    if role == AgentRole.IMAGE_POST.value:
        if not (cfg.get("image_prompt") or cfg.get("reminder_message")):
            raise ValueError("image_prompt_missing")

    if role == AgentRole.DM_ASSISTANT.value:
        mode = str(cfg.get("interaction_mode") or "command").strip().lower()
        scope = str(cfg.get("scope") or cfg.get("delivery_mode") or "dm").strip().lower()
        if mode in {"command", "both"} and not normalize_dm_command(cfg.get("dm_command")):
            raise ValueError("dm_command_missing")
        if mode in {"support", "both"} and not (
            cfg.get("support_instructions")
            or cfg.get("reminder_message")
            or agent.instruction_text
        ):
            raise ValueError("support_instructions_missing")
        if mode == "command" and not (
            cfg.get("reminder_message")
            or cfg.get("search_topic")
            or cfg.get("image_prompt")
            or cfg.get("support_instructions")
        ):
            raise ValueError("dm_action_missing")
        if scope in {"group", "both"} and not agent.max_chat_id:
            raise ValueError("group_chat_missing")

    if role == AgentRole.GROUP_MODERATION.value:
        sw = cfg.get("moderation_stop_words") or (cfg.get("moderation_rules") or {}).get("stop_words")
        block_links = cfg.get("moderation_block_links") or (cfg.get("moderation_rules") or {}).get("block_links")
        if not sw and not block_links:
            raise ValueError("moderation_rules_missing")

    if role in SCHEDULED_ROLES and role not in {
        AgentRole.NEWS_DIGEST.value,
        AgentRole.IMAGE_POST.value,
    }:
        if not cfg.get("reminder_message"):
            raise ValueError("message_missing")

    if profile.needs_group or role in GROUP_ROLES:
        if not agent.max_chat_id:
            raise ValueError("group_chat_missing")

    if role in EVENT_DRIVEN_ROLES and role != AgentRole.DM_ASSISTANT.value:
        if role == AgentRole.GROUP_MODERATION.value and cfg.get("bot_is_group_admin") is False:
            raise ValueError("bot_admin_missing")


def activation_summary(agent: AgentInstance) -> str:
    cfg = _config(agent)
    role_label = SUPPORTED_ROLE_LABELS.get(agent.role or "", agent.role or "агент")
    from app.services.agent.schedule import format_run_at_local

    lines = ["Агент активирован.", f"Задача: {role_label}."]

    if agent.role in SCHEDULED_ROLES:
        schedule = cfg.get("schedule_text", "—")
        tz_name = str(cfg.get("timezone") or "Europe/Moscow")
        lines.append(f"Расписание: {schedule}.")
        lines.append(f"Часовой пояс: {tz_name}.")
        next_run_raw = cfg.get("next_run_at")
        if next_run_raw:
            try:
                from datetime import datetime
                from datetime import timezone as dt_tz

                run_dt = datetime.fromisoformat(str(next_run_raw))
                if run_dt.tzinfo is None:
                    run_dt = run_dt.replace(tzinfo=dt_tz.utc)
                lines.append(f"Ближайший запуск: {format_run_at_local(run_dt, tz_name)}.")
            except ValueError:
                pass

    if cfg.get("search_topic"):
        lines.append(f"Тема: {cfg['search_topic']}.")
    if cfg.get("image_prompt"):
        lines.append(f"Промпт изображения: {str(cfg['image_prompt'])[:120]}.")
    if cfg.get("reminder_message"):
        from app.services.agent.generate_content import wants_llm_generated_content

        msg = str(cfg["reminder_message"])
        if cfg.get("content_pipeline") == "llm_generate" or wants_llm_generated_content(msg):
            lines.append(f"Контент: бот сгенерирует текст по запросу «{msg}».")
        else:
            lines.append(f"Текст: {msg}.")
    if normalize_dm_command(cfg.get("dm_command")):
        lines.append(f"Команда в MAX: /{normalize_dm_command(cfg.get('dm_command'))}.")
    if agent.max_chat_id:
        lines.append(f"Групповой чат MAX: {agent.max_chat_id}.")
    if agent.role == AgentRole.GROUP_MODERATION.value:
        lines.append("Модерация активна: бот следит за новыми сообщениями в группе.")
    if agent.role == AgentRole.DM_ASSISTANT.value:
        scope = str(cfg.get("scope") or "dm")
        mode = str(cfg.get("interaction_mode") or "command")
        if scope in {"group", "both"}:
            lines.append("Бот отвечает в группе MAX (нужны права админа).")
        if scope in {"dm", "both"}:
            if mode == "support":
                lines.append("Пишите боту в личке — он ответит на любое сообщение.")
            elif mode == "both":
                lines.append("В личке: команда или обычный вопрос; можно прислать фото для OCR/перевода.")
            else:
                lines.append("Напишите команду боту в личке MAX, чтобы получить ответ.")
        kb = cfg.get("knowledge_chunk_count")
        if kb:
            lines.append(f"База знаний: {kb} фрагментов из загруженных документов.")

    lines.append("Напишите **отключи агента**, чтобы остановить.")
    return "\n".join(lines)
