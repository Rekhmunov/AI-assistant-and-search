"""Возможности агента MAX: внутренняя модель и подсказки для диалога."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole

# Внутренние роли → понятные пользователю названия задач
USER_TASK_LABELS = {
    AgentRole.PERSONAL_REMINDER.value: "уведомления в ваш личный чат MAX",
    AgentRole.GROUP_REMINDER.value: "сообщения в группу MAX",
    AgentRole.GROUP_MESSAGE_LOG.value: "сводки из группы в ваш личный чат MAX",
}

GROUP_ROLES = frozenset(
    {
        AgentRole.GROUP_REMINDER.value,
        AgentRole.GROUP_MESSAGE_LOG.value,
    }
)

CAPABILITIES_REPLY = (
    "Сейчас агент Glosix в MAX умеет:\n"
    "• присылать вам уведомления в личный чат — по расписанию или разово;\n"
    "• публиковать сообщения в группе, где бот Glosix — администратор;\n"
    "• читать сообщения такой группы и присылать вам краткие сводки в личку;\n"
    "• работать по расписанию с учётом вашего часового пояса.\n\n"
    "Опишите задачу своими словами — помогу настроить."
)

_CLARIFICATION_MARKERS = (
    "не совсем понял",
    "не понял",
    "не поняла",
    "не понимаю",
    "неясно",
    "что дальше",
    "что делать",
    "что нужно",
    "поясни",
    "поясните",
    "объясни",
    "объясните",
    "можно подробнее",
    "подробнее",
    "растолкуй",
    "а дальше",
    "и что",
    "зачем это",
)

_CAPABILITIES_QUESTION_MARKERS = (
    "что умеешь",
    "ты умеешь",
    "что умеет",
    "что можешь",
    "ты можешь",
    "что может",
    "какие возможност",
    "что доступно",
    "что поддержива",
    "что ты делаешь",
    "чем можешь помочь",
    "чем помочь",
    "какие функции",
    "какие сценарии",
    "whitelist",
    "вайтлист",
)


def user_needs_clarification(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(marker in low for marker in _CLARIFICATION_MARKERS)


def user_asks_capabilities(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(marker in low for marker in _CAPABILITIES_QUESTION_MARKERS)


def extract_chat_id(text: str) -> int | None:
    for match in re.finditer(r"-?\d{5,}", text or ""):
        try:
            return int(match.group(0))
        except ValueError:
            continue
    return None


def _mentions_admin(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in ("админ", "администратор", "admin"))


def _is_negative(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(
        token in low
        for token in (
            "не админ",
            "не является",
            "неявляется",
            "нет",
            "не ",
            "no ",
            "false",
        )
    )


def _is_positive(text: str) -> bool:
    low = (text or "").strip().lower()
    if low in {"да", "yes", "ага", "угу", "верно", "подтверждаю", "есть", "добавил", "добавлен", "добавила"}:
        return True
    return any(
        phrase in low
        for phrase in (
            "является админ",
            "есть админ",
            "уже админ",
            "назначен админ",
            "добавил бот",
            "добавлен бот",
            "бот админ",
        )
    )


def _mentions_read_access(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in ("читать", "чтение", "read", "доступ к сообщ"))


def apply_message_hints(checklist: dict[str, Any], text: str) -> dict[str, Any]:
    """Извлекает из реплики пользователя поля чеклиста без участия LLM."""
    data = dict(checklist)
    clean = (text or "").strip()
    if not clean:
        return data

    chat_id = extract_chat_id(clean)
    if chat_id is not None:
        data["max_chat_id"] = chat_id

    role = data.get("role")
    if role in GROUP_ROLES and _mentions_admin(clean):
        if _is_negative(clean):
            data["bot_is_group_admin"] = False
        elif _is_positive(clean):
            data["bot_is_group_admin"] = True
    elif role in GROUP_ROLES and _is_positive(clean) and not _is_negative(clean):
        # Короткое «да» после вопроса про админа
        data["bot_is_group_admin"] = True

    if role == AgentRole.GROUP_MESSAGE_LOG.value and _mentions_read_access(clean):
        if _is_negative(clean):
            data["bot_can_read_messages"] = False
        elif _is_positive(clean):
            data["bot_can_read_messages"] = True

    return data


def explain_next_step(checklist: dict[str, Any]) -> str:
    """Пояснение следующего шага без сброса диалога (fallback при сбое LLM)."""
    role = checklist.get("role")
    task = USER_TASK_LABELS.get(role or "", "настройку агента")
    known: list[str] = []
    if role:
        known.append(f"Задача: {task}.")
    if checklist.get("max_chat_id"):
        known.append(f"Группа MAX: {checklist['max_chat_id']}.")
    if checklist.get("schedule_text"):
        known.append(f"Расписание: {checklist['schedule_text']}.")
    if checklist.get("reminder_message"):
        known.append(f"Текст сообщения: {checklist['reminder_message']}.")
    if checklist.get("timezone"):
        known.append(f"Часовой пояс: {checklist['timezone']}.")

    intro = " ".join(known) if known else "Продолжаем настройку агента."

    if not role:
        return (
            f"{intro}\n\n"
            "Опишите, что должен делать агент — например, напоминать вам в личку "
            "или писать в группу MAX."
        )

    if not checklist.get("schedule_text"):
        return (
            f"{intro}\n\n"
            "Уточните, **когда** агент должен срабатывать: например «каждый день в 9:00», "
            "«завтра в 10:15» или «через 30 минут»."
        )

    if checklist.get("schedule_text") and not checklist.get("timezone"):
        return (
            f"{intro}\n\n"
            "Нужен ваш **часовой пояс** (например Europe/Moscow или UTC+3), "
            "чтобы время срабатывания было верным."
        )

    if not checklist.get("reminder_message"):
        label = "сводки" if role == AgentRole.GROUP_MESSAGE_LOG.value else "сообщения"
        return (
            f"{intro}\n\n"
            f"Напишите **текст {label}**, который бот будет отправлять."
        )

    if role in GROUP_ROLES and not checklist.get("max_chat_id"):
        return (
            f"{intro}\n\n"
            "Укажите **ID группы MAX** (число из информации о чате) "
            "или добавьте бота Glosix в группу — ID подтянется автоматически."
        )

    if role in GROUP_ROLES and checklist.get("bot_is_group_admin") is not True:
        return (
            f"{intro}\n\n"
            "Проверьте, что **бот Glosix — администратор** группы: "
            "MAX → группа → «Информация о группе» → «Администраторы». "
            "Напишите «да», когда бот добавлен."
        )

    if role == AgentRole.GROUP_MESSAGE_LOG.value and checklist.get("bot_can_read_messages") is not True:
        return (
            f"{intro}\n\n"
            "Для сводок боту нужно **право читать сообщения** в группе. "
            "Включите его в настройках администратора бота и напишите «да»."
        )

    return (
        f"{intro}\n\n"
        "Если всё верно — напишите «да» или «подтверждаю», и я запущу агента."
    )


def build_parse_fallback_reply(checklist: dict[str, Any], user_text: str) -> str:
    if user_asks_capabilities(user_text):
        return CAPABILITIES_REPLY
    if user_needs_clarification(user_text):
        return (
            "Поясню проще, без начала сначала.\n\n"
            + explain_next_step(checklist)
        )
    missing_reply = explain_next_step(checklist)
    if "Продолжаем настройку агента" not in missing_reply:
        return missing_reply
    return (
        "Продолжим настройку с того места, где остановились.\n\n"
        + explain_next_step(checklist)
    )
