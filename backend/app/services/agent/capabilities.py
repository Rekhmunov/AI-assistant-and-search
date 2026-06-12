"""Возможности агента MAX: внутренняя модель и подсказки для диалога."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole
from app.services.agent.intent_hints import DEFAULT_AGENT_TIMEZONE
from app.services.agent.profile import GROUP_ROLES as PROFILE_GROUP_ROLES
from app.services.agent.profile import USER_TASK_LABELS

GROUP_ROLES = PROFILE_GROUP_ROLES

_ACTIVATION_CLAIM_MARKERS = (
    "агент запущен",
    "агент активирован",
    "принято!",
    "запущен.",
    "уже работает",
)

_CAPABILITIES_TEMPLATE_MARKERS = (
    "сейчас агент glosix в max умеет",
    "присылать уведомления и напоминания в личный чат",
    "напишите одним сообщением, что нужно вам",
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

_CAPABILITY_LIST_MARKERS = (
    "что умеешь",
    "что ты умеешь",
    "ты умеешь",
    "что умеет",
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

# Конкретная задача в вопросе — не список возможностей, а «можешь ли X?»
_TASK_HINT_RE = re.compile(
    r"(напомин|уведом|новост|модерац|сводк|картин|изображ|групп|поддержк|faq|команд|"
    r"перевед|распозна|спам|удал|сообщен|чат|бот)",
    re.I,
)

_FEASIBILITY_RE = re.compile(
    r"(?:^|\s)(?:ты\s+)?(?:можешь|умеешь|сможешь|получится|"
    r"можно\s+ли|возможно\s+ли|есть\s+ли|поддерживаешь\s+ли|умеешь\s+ли|можешь\s+ли)\b",
    re.I,
)

_IMMEDIATE_LOOKUP_RE = re.compile(
    r"(?:"
    r"\b(?:найди|найти|поищи|поиск|узнай|узнать|проверь|посмотри|покажи)\b"
    r"|\bв\s+интернет"
    r"|\bскажи\s+(?:мне\s+)?(?:какой|сколько|что|когда|где)\b"
    r"|\bотправь\b|\bпришли\b|\bнапиши\s+сейчас\b"
    r")",
    re.I,
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


def _has_task_hint(text: str) -> bool:
    return bool(_TASK_HINT_RE.search(text or ""))


def user_wants_immediate_lookup(text: str) -> bool:
    """Сейчас нужен факт из интернета, а не вопрос «можешь ли настроить агента»."""
    low = (text or "").strip().lower()
    if not low:
        return False
    return bool(_IMMEDIATE_LOOKUP_RE.search(low))


def user_asks_feasibility(text: str) -> bool:
    """
    «Ты можешь сделать напоминание?» — вопрос про конкретную задачу, не про список возможностей.
    """
    low = (text or "").strip().lower()
    if not low or not _FEASIBILITY_RE.search(low):
        return False
    if user_wants_immediate_lookup(low):
        return False
    return _has_task_hint(low)


def user_asks_capabilities(text: str) -> bool:
    """Только запрос списка возможностей («что умеешь»), без конкретной задачи."""
    low = (text or "").strip().lower()
    if not low or user_asks_feasibility(text):
        return False
    if any(marker in low for marker in _CAPABILITY_LIST_MARKERS):
        return True
    if ("что можешь" in low or "ты можешь" in low) and not _has_task_hint(low):
        return True
    return False


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


def _ensure_timezone(checklist: dict[str, Any]) -> dict[str, Any]:
    data = dict(checklist)
    if data.get("schedule_text") and not data.get("timezone"):
        data["timezone"] = DEFAULT_AGENT_TIMEZONE
    return data


def reply_claims_activation(reply: str) -> bool:
    low = (reply or "").lower()
    return any(marker in low for marker in _ACTIVATION_CLAIM_MARKERS)


def reply_looks_like_capabilities_template(reply: str) -> bool:
    low = (reply or "").lower()
    return any(marker in low for marker in _CAPABILITIES_TEMPLATE_MARKERS)


def compose_feasibility_reply(checklist: dict[str, Any], user_text: str) -> str | None:
    """Живой ответ на «ты можешь…?» когда LLM недоступен."""
    if not user_asks_feasibility(user_text):
        return None
    hinted = _ensure_timezone(apply_message_hints(checklist, user_text))
    role = hinted.get("role")
    if role == AgentRole.PERSONAL_REMINDER.value:
        if hinted.get("schedule_text") and hinted.get("reminder_message"):
            tz = hinted.get("timezone") or DEFAULT_AGENT_TIMEZONE
            return (
                f"Да, напоминания в личный чат MAX — это как раз моя задача. "
                f"Записал: «{hinted['reminder_message']}», {hinted['schedule_text']} ({tz}). "
                "Если всё верно — напишите «запустить»."
            )
        return (
            "Да, могу присылать напоминания в ваш личный чат MAX по расписанию. "
            "Напишите, когда и с каким текстом — например «каждый день в 9:00, текст: встреча»."
        )
    if role == AgentRole.GROUP_REMINDER.value:
        if (
            hinted.get("max_chat_id")
            and hinted.get("reminder_message")
            and hinted.get("schedule_text")
        ):
            return (
                f"Да, отправлю «{hinted['reminder_message']}» в группу MAX "
                f"({hinted['max_chat_id']}), {hinted['schedule_text']}. "
                "Если всё верно — напишите «да»."
            )
        if hinted.get("max_chat_id") and hinted.get("reminder_message"):
            return (
                f"Да, напишу «{hinted['reminder_message']}» в группу {hinted['max_chat_id']}. "
                "Когда отправить — сейчас или по расписанию?"
            )
        return (
            "Да, могу публиковать сообщения в группу MAX — бот должен быть админом. "
            "Пришлите ссылку на группу и текст сообщения."
        )
    if role == AgentRole.NEWS_DIGEST.value:
        parts = ["Да, могу публиковать новости в MAX"]
        if hinted.get("delivery_mode") == "group":
            parts.append("в группу")
        if hinted.get("content_pipeline") == "web_digest_images":
            parts.append("с текстом и иллюстрациями")
        if hinted.get("schedule_text"):
            return (
                f"{' '.join(parts)} — {hinted['schedule_text']}. "
                "Если всё верно — напишите «да»."
            )
        return (
            f"{' '.join(parts)}. "
            "Укажите тему, группу (если нужно) и расписание — например «раз в час»."
        )
    return (
        "Да, в MAX это можно настроить — напоминания, посты в группу, новости, модерация, "
        "ответы с распознаванием текста с фото. Опишите задачу одним сообщением."
    )


def apply_message_hints(checklist: dict[str, Any], text: str) -> dict[str, Any]:
    """Извлекает из реплики пользователя поля чеклиста без участия LLM."""
    from app.services.agent.intent_hints import infer_checklist_fields
    from app.services.agent.operational import is_assist_turn

    data = dict(checklist)
    clean = (text or "").strip()
    if not clean:
        return data

    if is_assist_turn(clean):
        from app.services.agent.intent_hints import _extract_max_chat_id

        chat_id = extract_chat_id(clean) or _extract_max_chat_id(clean)
        if chat_id is not None:
            data["max_chat_id"] = chat_id
        data["role"] = None
        for key in ("interaction_mode", "scope", "support_instructions", "dm_command"):
            data.pop(key, None)
        return _ensure_timezone(data)

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

    return _ensure_timezone(data)


def _checklist_intro(checklist: dict[str, Any]) -> str:
    if str(checklist.get("task_mode") or "").lower() == "expense_tracker":
        cats = checklist.get("expense_categories") or []
        cat_hint = f" Категорий: {len(cats)}." if cats else ""
        return (
            "Понял задачу: **учёт затрат в группе MAX** — формат «Сумма + описание», "
            f"категоризация, Excel-отчёт по запросу.{cat_hint}"
        )
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
        from app.services.agent.generate_content import wants_llm_generated_content

        msg = str(checklist["reminder_message"])[:80]
        if wants_llm_generated_content(str(checklist["reminder_message"])):
            parts.append(f"Контент: генерируется — «{msg}».")
        else:
            parts.append(f"Текст: {msg}.")
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

    if role == AgentRole.NEWS_DIGEST.value and str(checklist.get("content_pipeline") or "") == "web_digest_images":
        if checklist.get("delivery_mode") == "group" and not checklist.get("max_chat_id"):
            return (
                f"{intro}\n\n"
                "Пришлите **ссылку на группу MAX** (web.max.ru/-ID) или добавьте бота Glosix в группу."
            )
        if checklist.get("delivery_mode") == "group" and checklist.get("bot_is_group_admin") is not True:
            return f"{intro}\n\nСделайте **Glosix администратором** группы в MAX и напишите «да»."

    if role == AgentRole.IMAGE_POST.value and not (
        checklist.get("image_prompt") or checklist.get("reminder_message")
    ):
        return f"{intro}\n\n**Что рисовать** на картинках? Опишите стиль и сюжет."

    from app.services.agent.profile import SCHEDULED_ROLES

    if role in SCHEDULED_ROLES and not checklist.get("schedule_text"):
        return (
            f"{intro}\n\n"
            "Уточните, **когда** агент должен срабатывать: например «каждый час», "
            "«каждый день в 9:00», «завтра в 10:15» или «через 30 минут»."
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
    Резервный ответ без LLM — только при сбое модели.
    Обычный диалог всегда идёт через LLM (живые формулировки).
    """
    if user_asks_capabilities(user_text) or user_asks_feasibility(user_text):
        return None

    hinted = apply_message_hints(checklist, user_text)
    step = explain_next_step(hinted, user_text=user_text)

    if user_needs_clarification(user_text) or user_wants_continue(user_text):
        prefix = "Поясню проще.\n\n" if user_needs_clarification(user_text) else ""
        return prefix + step

    if hinted.get("role"):
        return step

    return None


def build_parse_fallback_reply(checklist: dict[str, Any], user_text: str) -> str:
    feas = compose_feasibility_reply(checklist, user_text)
    if feas:
        return feas
    local = try_local_onboarding_reply(checklist, user_text)
    if local:
        return local
    return explain_next_step(apply_message_hints(checklist, user_text), user_text=user_text)
