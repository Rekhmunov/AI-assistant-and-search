"""Сбор параметров агента (MVP: правила + парсер расписания)."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.services.agent.constants import CANCEL_PHRASES, SUPPORTED_ROLE_LABELS
from app.services.agent.schedule import parse_reminder_schedule

_ROLE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (AgentRole.PERSONAL_REMINDER.value, ("личн", "себе", "мне напомни", "в max", "в макс", "glosix")),
    (AgentRole.GROUP_REMINDER.value, ("групп", "в чате групп", "в группе")),
    (
        AgentRole.GROUP_MESSAGE_LOG.value,
        ("сообщени", "учёт", "учет", "сводк", "отчёт", "отчет", "читать групп", "монитор"),
    ),
]


def user_wants_cancel(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(phrase in low for phrase in CANCEL_PHRASES)


def detect_role(text: str) -> str | None:
    low = (text or "").strip().lower()
    if not low:
        return None
    for role, patterns in _ROLE_PATTERNS:
        if any(p in low for p in patterns):
            return role
    return None


def _config(agent: AgentInstance) -> dict[str, Any]:
    raw = agent.config
    return dict(raw) if isinstance(raw, dict) else {}


def _save_config(agent: AgentInstance, config: dict[str, Any]) -> None:
    agent.config = config


def _extract_chat_id(text: str) -> int | None:
    for match in re.finditer(r"-?\d{5,}", text or ""):
        try:
            return int(match.group(0))
        except ValueError:
            continue
    return None


def _missing_fields(agent: AgentInstance) -> list[str]:
    cfg = _config(agent)
    missing: list[str] = []
    if not agent.role:
        missing.append("role")
    if not cfg.get("schedule_text"):
        missing.append("schedule")
    if not cfg.get("reminder_message"):
        missing.append("message")
    if agent.role in {AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MESSAGE_LOG.value}:
        if not agent.max_chat_id and not cfg.get("max_chat_id"):
            missing.append("group_chat")
    return missing


def _question_for(field: str, agent: AgentInstance) -> str:
    if field == "role":
        lines = "\n".join(f"• {label}" for label in SUPPORTED_ROLE_LABELS.values())
        return f"Выберите задачу агента:\n{lines}"
    if field == "schedule":
        return (
            "Когда напоминать? Например: «каждый понедельник в 10:00», "
            "«завтра в 9:00» или «2026-06-10 14:30»."
        )
    if field == "message":
        if agent.role == AgentRole.GROUP_MESSAGE_LOG.value:
            return "Какой текст сводки присылать вам в личный чат MAX?"
        return "Какой текст напоминания отправлять?"
    if field == "group_chat":
        return (
            "Добавьте бота Glosix администратором в группу MAX (с правом читать сообщения для сводок). "
            "Затем укажите ID группового чата или перешлите сюда любое сообщение из группы с числовым ID."
        )
    return "Уточните параметры агента."


def apply_user_message(agent: AgentInstance, text: str) -> str | None:
    """
    Обновляет agent по сообщению пользователя.
    Возвращает следующий вопрос или None, если все поля собраны.
    """
    cfg = _config(agent)
    clean = (text or "").strip()
    if not clean:
        return _question_for("role", agent)

    if not agent.role:
        role = detect_role(clean)
        if role:
            agent.role = role
            agent.status = AgentStatus.COLLECTING.value
        else:
            return _question_for("role", agent)

    if not cfg.get("schedule_text"):
        if any(k in clean.lower() for k in ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье", "завтра", ":", "час")) or re.search(
            r"\d{4}-\d{2}-\d{2}", clean
        ):
            cfg["schedule_text"] = clean
        elif agent.instruction_text:
            cfg["schedule_text"] = clean
        _save_config(agent, cfg)

    if not cfg.get("reminder_message"):
        if cfg.get("schedule_text") and clean != cfg.get("schedule_text"):
            cfg["reminder_message"] = clean
            _save_config(agent, cfg)
        elif agent.role == AgentRole.GROUP_MESSAGE_LOG.value and cfg.get("schedule_text"):
            cfg["reminder_message"] = "Сводка новых сообщений в группе Glosix."
            _save_config(agent, cfg)

    if agent.role in {AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MESSAGE_LOG.value}:
        chat_id = _extract_chat_id(clean)
        if chat_id is not None:
            agent.max_chat_id = chat_id
            cfg["max_chat_id"] = chat_id
            _save_config(agent, cfg)
        elif cfg.get("registered_group_chat_id"):
            agent.max_chat_id = int(cfg["registered_group_chat_id"])
            _save_config(agent, cfg)

    if not agent.instruction_text:
        agent.instruction_text = clean
    else:
        agent.instruction_text = f"{agent.instruction_text}\n{clean}"

    missing = _missing_fields(agent)
    if missing:
        return _question_for(missing[0], agent)
    return None


def validate_activation(agent: AgentInstance) -> None:
    cfg = _config(agent)
    if not agent.role:
        raise ValueError("role_missing")
    if not cfg.get("schedule_text"):
        raise ValueError("schedule_missing")
    if not cfg.get("reminder_message"):
        raise ValueError("message_missing")
    parse_reminder_schedule(str(cfg["schedule_text"]))
    if agent.role in {AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MESSAGE_LOG.value}:
        if not agent.max_chat_id:
            raise ValueError("group_chat_missing")


def activation_summary(agent: AgentInstance) -> str:
    cfg = _config(agent)
    role_label = SUPPORTED_ROLE_LABELS.get(agent.role or "", agent.role or "агент")
    schedule = cfg.get("schedule_text", "—")
    message = cfg.get("reminder_message", "—")
    lines = [
        "Агент активирован.",
        f"Задача: {role_label}.",
        f"Расписание: {schedule}.",
        f"Текст: {message}.",
    ]
    if agent.max_chat_id:
        lines.append(f"Групповой чат MAX: {agent.max_chat_id}.")
    lines.append("Напишите «отключи агента», чтобы остановить.")
    return "\n".join(lines)
