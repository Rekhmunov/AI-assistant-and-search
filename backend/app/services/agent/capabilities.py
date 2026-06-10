"""Возможности агента MAX: внутренняя модель и подсказки для диалога."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole
from app.services.agent.profile import GROUP_ROLES as PROFILE_GROUP_ROLES
from app.services.agent.profile import USER_TASK_LABELS

GROUP_ROLES = PROFILE_GROUP_ROLES

CAPABILITIES_REPLY = (
    "Сейчас агент Glosix в MAX умеет:\n"
    "• присылать уведомления и напоминания в личный чат — по расписанию;\n"
    "• публиковать сообщения и картинки в группе (бот — администратор);\n"
    "• собирать сводки из группы и новости по теме из интернета;\n"
    "• модерировать группу (удалять сообщения по правилам);\n"
    "• отвечать в личке и в группе как поддержка — в том числе распознавать текст с фото;\n"
    "• выполнять команды в личке (например /новости — если настроите команду).\n\n"
    "Напишите **одним сообщением**, что нужно вам — например:\n"
    "• «напоминай мне каждый день в 9:00 про встречу»\n"
    "• «отвечай в группе на вопросы по FAQ, распознавай текст с фото»\n"
    "• «присылай новости про ИИ каждое утро»"
)

_CONTINUE_MARKERS = (
    "продолж",
    "дальше",
    "поехали",
    "давай",
    "начн",
    "готов",
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


def user_wants_continue(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if low in {"ок", "okay", "ok", "да", "ага", "угу"}:
        return True
    return any(marker in low for marker in _CONTINUE_MARKERS)


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
    from app.services.agent.intent_hints import infer_checklist_fields

    data = dict(checklist)
    clean = (text or "").strip()
    if not clean:
        return data

    data = infer_checklist_fields(clean, data)

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


def _checklist_intro(checklist: dict[str, Any]) -> str:
    role = checklist.get("role")
    task = USER_TASK_LABELS.get(role or "", "")
    parts: list[str] = []
    if role and task:
        parts.append(f"Понял задачу: **{task}**.")
    if checklist.get("scope"):
        parts.append(f"Где работает: {checklist['scope']}.")
    if checklist.get("interaction_mode"):
        parts.append(f"Режим: {checklist['interaction_mode']}.")
    if checklist.get("max_chat_id"):
        parts.append(f"Группа MAX: {checklist['max_chat_id']}.")
    if checklist.get("schedule_text"):
        parts.append(f"Расписание: {checklist['schedule_text']}.")
    if checklist.get("reminder_message"):
        parts.append(f"Текст: {str(checklist['reminder_message'])[:80]}.")
    if checklist.get("timezone"):
        parts.append(f"Часовой пояс: {checklist['timezone']}.")
    return " ".join(parts)


def explain_next_step(checklist: dict[str, Any], *, user_text: str = "") -> str:
    """Пояснение следующего шага без сброса диалога (fallback при сбое LLM)."""
    role = checklist.get("role")
    intro = _checklist_intro(checklist)

    if not role:
        if user_wants_continue(user_text) or user_needs_clarification(user_text):
            return (
                (intro + "\n\n" if intro else "")
                + "Чтобы продолжить, опишите задачу **одним сообщением**. Примеры:\n"
                "• «напоминай мне в 9:00 каждый день»\n"
                "• «отвечай в группе на вопросы, умеешь читать текст с фото»\n"
                "• «удаляй спам и ссылки в группе»"
            )
        return (
            (intro + "\n\n" if intro else "")
            + "Опишите задачу **своими словами** — что бот должен делать в MAX. "
            "Можно одной фразой: напоминания, группа, новости, поддержка, модерация."
        )

    if role == AgentRole.DM_ASSISTANT.value:
        scope = str(checklist.get("scope") or "dm").lower()
        mode = str(checklist.get("interaction_mode") or "command").lower()
        if scope in {"group", "both"} and not checklist.get("max_chat_id"):
            return (
                f"{intro}\n\n"
                "Добавьте бота Glosix в **группу MAX** (как администратора) "
                "или пришлите **ID группы** — подтянется автоматически."
            )
        if scope in {"group", "both"} and checklist.get("bot_is_group_admin") is not True:
            return (
                f"{intro}\n\n"
                "Сделайте **Glosix администратором** группы в MAX и напишите «да»."
            )
        if mode in {"command", "both"} and not checklist.get("dm_command"):
            return (
                f"{intro}\n\n"
                "Придумайте **команду** для бота (латиницей), например `faq` или `news` — "
                "пользователи будут писать `/faq`."
            )
        if mode in {"support", "both"} and not (
            checklist.get("support_instructions") or checklist.get("reminder_message")
        ):
            return (
                f"{intro}\n\n"
                "Опишите, **как бот должен отвечать**: тон, темы, что делать с фото. "
                "Можно прикрепить FAQ-документ кнопкой «+» в этом треде."
            )
        return f"{intro}\n\nЕсли всё верно — напишите «да» или «подтверждаю»."

    if role == AgentRole.GROUP_MODERATION.value:
        if not checklist.get("moderation_stop_words") and not checklist.get("moderation_block_links"):
            return (
                f"{intro}\n\n"
                "Какие **правила модерации**? Например: стоп-слова через запятую "
                "или «блокировать ссылки»."
            )
        if not checklist.get("max_chat_id"):
            return (
                f"{intro}\n\n"
                "Укажите группу MAX — добавьте бота в группу или пришлите ID чата."
            )
        if checklist.get("bot_is_group_admin") is not True:
            return f"{intro}\n\nНазначьте **Glosix администратором** группы и напишите «да»."

    if role == AgentRole.NEWS_DIGEST.value and not (
        checklist.get("search_topic") or checklist.get("reminder_message")
    ):
        return f"{intro}\n\nПо **какой теме** собирать новости? Например: «нейросети», «курс доллара»."

    if role == AgentRole.IMAGE_POST.value and not (
        checklist.get("image_prompt") or checklist.get("reminder_message")
    ):
        return f"{intro}\n\n**Что рисовать** на картинках? Опишите стиль и сюжет."

    from app.services.agent.profile import SCHEDULED_ROLES

    if role in SCHEDULED_ROLES and not checklist.get("schedule_text"):
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

    if role in SCHEDULED_ROLES and not checklist.get("reminder_message"):
        if role == AgentRole.GROUP_MESSAGE_LOG.value:
            label = "заголовка сводки"
        elif role in {AgentRole.NEWS_DIGEST.value, AgentRole.IMAGE_POST.value}:
            label = "сообщения (или оставьте пустым — подставим тему)"
        else:
            label = "сообщения"
        return f"{intro}\n\nНапишите **текст {label}**, который бот будет отправлять."

    if role in GROUP_ROLES and not checklist.get("max_chat_id"):
        return (
            f"{intro}\n\n"
            "Укажите **ID группы MAX** (число из информации о чате) "
            "или добавьте бота Glosix в группу — ID подтянется автоматически."
        )

    if role in GROUP_ROLES and checklist.get("bot_is_group_admin") is not True:
        if checklist.get("bot_is_group_admin") is False:
            lead = (
                "Бот пока не администратор — это можно исправить за минуту.\n\n"
                "1. Откройте группу в MAX.\n"
                "2. «Информация о группе» → «Администраторы».\n"
                "3. Добавьте **Glosix** в администраторы.\n\n"
            )
        else:
            lead = (
                "Проверьте, что **бот Glosix — администратор** группы: "
                "MAX → группа → «Информация о группе» → «Администраторы».\n\n"
            )
        return f"{intro}\n\n{lead}Напишите «да», когда бот добавлен."

    if role == AgentRole.GROUP_MESSAGE_LOG.value and checklist.get("bot_can_read_messages") is not True:
        if checklist.get("bot_can_read_messages") is False:
            lead = (
                "Право читать сообщения пока не выдано — включите его в MAX:\n"
                "группа → администраторы → Glosix → разрешение **читать сообщения**.\n\n"
            )
        else:
            lead = (
                "Для сводок боту нужно **право читать сообщения** в группе. "
                "Включите его в настройках администратора бота.\n\n"
            )
        return f"{intro}\n\n{lead}Напишите «да», когда доступ включён."

    return (
        f"{intro}\n\n"
        "Если всё верно — напишите «да» или «подтверждаю», и я запущу агента."
    )


def try_local_onboarding_reply(checklist: dict[str, Any], user_text: str) -> str | None:
    """
    Ответ без LLM, если из текста уже понятен следующий шаг.
    Возвращает None, если лучше вызвать LLM.
    """
    hinted = apply_message_hints(checklist, user_text)
    if user_asks_capabilities(user_text):
        return CAPABILITIES_REPLY

    step = explain_next_step(hinted, user_text=user_text)
    intro = _checklist_intro(hinted)

    if hinted.get("role") and hinted.get("role") != checklist.get("role"):
        return f"Записал.\n\n{step}"

    if user_needs_clarification(user_text) or user_wants_continue(user_text):
        prefix = "Поясню проще.\n\n" if user_needs_clarification(user_text) else ""
        return prefix + step

    if hinted.get("role") and intro:
        return step

    if len((user_text or "").strip()) >= 12 and not hinted.get("role"):
        return step

    return None


def build_parse_fallback_reply(checklist: dict[str, Any], user_text: str) -> str:
    local = try_local_onboarding_reply(checklist, user_text)
    if local:
        return local
    return explain_next_step(apply_message_hints(checklist, user_text), user_text=user_text)
