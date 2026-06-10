"""Локальное распознавание намерения пользователя при настройке агента."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole
from app.services.agent.profile import GROUP_ROLES

_SCHEDULE_RE = re.compile(
    r"(кажд\w+\s+(?:день|утр|вечер|недел|понедельник|вторник|сред|четверг|пятниц|суббот|воскресен))"
    r"|(?:завтра|послезавтра|через\s+\d+)"
    r"|(?:\d{1,2}[:.]\d{2})"
    r"|(?:в\s+\d{1,2}\s*час)",
    re.I,
)

_TZ_RE = re.compile(r"(europe/moscow|utc[+-]\d+|москв\w*|msk)", re.I)


def _has_any(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def infer_role_from_text(text: str) -> str | None:
    """Эвристика: определить role по свободной формулировке задачи."""
    clean = (text or "").strip()
    low = clean.lower()
    has_reminder = _has_any(low, "напомин", "уведом")
    min_len = 5 if has_reminder else 8
    if len(clean) < min_len:
        return None

    if has_reminder:
        if _has_any(low, "групп") and not _has_any(low, "своем чат", "своём чат", "личн", "мне"):
            return AgentRole.GROUP_REMINDER.value
        return AgentRole.PERSONAL_REMINDER.value

    if _has_any(low, "модерац", "удаляй сообщ", "удалять сообщ", "стоп-слов", "антиспам", "фильтр спам"):
        return AgentRole.GROUP_MODERATION.value

    if _has_any(
        low,
        "поддержк",
        "помощник",
        "отвечай",
        "ответь на",
        "faq",
        "база знан",
        "обратной связ",
        "распозна",
        "перевед",
        "ocr",
        "текст с картин",
        "текст с фото",
        "с картинки",
        "с фото",
    ):
        return AgentRole.DM_ASSISTANT.value

    if _has_any(low, "новост", "дайджест") and not _has_any(low, "групп", "сводк сообщ"):
        return AgentRole.NEWS_DIGEST.value

    if _has_any(low, "сгенерир", "генерир", "нарисуй", "картинк", "изображен", "фото") and _has_any(
        low, "отправ", "присылай", "публик", "пост"
    ):
        return AgentRole.IMAGE_POST.value

    if _has_any(low, "сводк", "итог дня", "резюме") and _has_any(low, "групп", "чат"):
        return AgentRole.GROUP_MESSAGE_LOG.value

    if _has_any(low, "групп", "чат") and _has_any(low, "сообщ", "пиши", "отправ"):
        return AgentRole.GROUP_REMINDER.value

    if _has_any(low, "пинг", "напиши мне", "присылай мне"):
        return AgentRole.PERSONAL_REMINDER.value

    if _has_any(low, "команд", "/") and _has_any(low, "бот", "личк", "max"):
        return AgentRole.DM_ASSISTANT.value

    return None


def infer_checklist_fields(text: str, data: dict[str, Any]) -> dict[str, Any]:
    """Дополняет чеклист полями из текста пользователя."""
    clean = (text or "").strip()
    if not clean:
        return data

    low = clean.lower()
    role = data.get("role") or infer_role_from_text(clean)
    if role and not data.get("role"):
        data["role"] = role

    sched = _SCHEDULE_RE.search(clean)
    if sched and not data.get("schedule_text"):
        data["schedule_text"] = sched.group(0).strip()

    tz = _TZ_RE.search(clean)
    if tz and not data.get("timezone"):
        raw = tz.group(0)
        if "москв" in raw.lower() or raw.lower() == "msk":
            data["timezone"] = "Europe/Moscow"
        else:
            data["timezone"] = raw.replace(" ", "")

    if role == AgentRole.NEWS_DIGEST.value and not data.get("search_topic"):
        if len(clean) > 12:
            data["search_topic"] = clean[:200]

    if role == AgentRole.IMAGE_POST.value and not data.get("image_prompt"):
        if len(clean) > 12:
            data["image_prompt"] = clean[:500]

    if role == AgentRole.DM_ASSISTANT.value:
        if _has_any(low, "групп", "чат") and not _has_any(low, "только личк", "только в личк"):
            if _has_any(low, "и личк", "и в личк", "оба", "везде"):
                data["scope"] = "both"
            else:
                data["scope"] = "group"
        elif _has_any(low, "личк", "личн", "диалог"):
            data.setdefault("scope", "dm")

        if _has_any(low, "на все", "любое сообщ", "любые сообщ", "поддержк", "как поддержк", "на вопрос"):
            data["interaction_mode"] = "support"
        elif _has_any(low, "команд", "/"):
            data["interaction_mode"] = "command"
        elif _has_any(low, "и команд", "команда и"):
            data["interaction_mode"] = "both"

        if not data.get("support_instructions") and _has_any(
            low, "отвечай", "помогай", "поддержк", "faq", "база", "перевед", "распозна"
        ):
            data["support_instructions"] = clean[:1500]

        if not data.get("reminder_message") and data.get("support_instructions"):
            data["reminder_message"] = data["support_instructions"][:500]

    if role in {AgentRole.PERSONAL_REMINDER.value, AgentRole.GROUP_REMINDER.value}:
        if not data.get("reminder_message") and len(clean) > 20 and not _SCHEDULE_RE.search(clean):
            data["reminder_message"] = clean[:500]
        elif not data.get("reminder_message") and _has_any(low, "текст", "напиши", "сообщени"):
            data["reminder_message"] = clean[:500]

    if role == AgentRole.GROUP_MODERATION.value:
        if _has_any(low, "ссылк", "url", "http"):
            data["moderation_block_links"] = True
        words = re.findall(r"[а-яёa-z]{4,}", low)
        stop = [w for w in words if w in {"спам", "реклама", "мат", "ругательств"}]
        if stop and not data.get("moderation_stop_words"):
            data["moderation_stop_words"] = ", ".join(stop)

    return data
