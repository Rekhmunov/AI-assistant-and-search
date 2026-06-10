"""Локальное распознавание намерения пользователя при настройке агента."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole

DEFAULT_AGENT_TIMEZONE = "Europe/Moscow"

_SCHEDULE_RE = re.compile(
    r"(кажд\w+\s+(?:день|утр|вечер|недел|понедельник|вторник|сред|четверг|пятниц|суббот|воскресен))"
    r"|(?:завтра|послезавтра|сегодня|через\s+\d+)"
    r"|(?:в\s+)?\d{1,2}[:.]\d{2}"
    r"|(?:в\s+\d{1,2}\s*час)",
    re.I,
)

_TIME_ONLY_RE = re.compile(r"(?:в\s+)?(\d{1,2})[:.](\d{2})", re.I)

_TZ_RE = re.compile(r"(europe/moscow|utc[+-]\d+|москв\w*|msk)", re.I)

_QUOTED_TEXT_RE = re.compile(
    r'[«""]([^«""]+)[»""]|текст\s+напоминан\w*\s+["«]([^"«]+)["»]',
    re.I,
)


def _has_any(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def user_corrects_understanding(text: str) -> bool:
    low = (text or "").lower()
    return any(
        p in low
        for p in (
            "неправильно",
            "не правильно",
            "не так",
            "не понял",
            "не поняла",
            "передумал",
            "исправь",
            "нет,",
            "нет ты",
        )
    )


def _is_personal_max_chat(low: str) -> bool:
    """
    Личный диалог пользователя с ботом Glosix в MAX (не группа пользователей).
    «Твоей группе» в обращении к боту часто означает «в твоём чате» — тоже личка.
    """
    if _has_any(
        low,
        "твоем чат",
        "твоём чат",
        "своем чат",
        "своём чат",
        "чате glosix",
        "чат glosix",
        "чате max",
        "чат max",
        "личк",
        "личн",
        "диалог с бот",
        "твоей группе",
        "твоей групп",
        "твоем чате",
        "твоём чате",
    ):
        return True
    return False


def _is_user_group(low: str) -> bool:
    """Группа пользователей в MAX (не личка с ботом)."""
    return _has_any(low, "моей групп", "нашей групп", "в группе", "групповой чат") and not _is_personal_max_chat(
        low
    )


def infer_role_from_text(text: str) -> str | None:
    """Эвристика: определить role по свободной формулировке задачи."""
    clean = (text or "").strip()
    low = clean.lower()
    has_reminder = _has_any(low, "напомин", "уведом")
    min_len = 5 if has_reminder else 8
    if len(clean) < min_len:
        return None

    if has_reminder:
        if _is_user_group(low):
            return AgentRole.GROUP_REMINDER.value
        if _is_personal_max_chat(low) or not _has_any(low, "групп"):
            return AgentRole.PERSONAL_REMINDER.value
        return AgentRole.GROUP_REMINDER.value

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

    if _is_user_group(low) and _has_any(low, "сообщ", "пиши", "отправ"):
        return AgentRole.GROUP_REMINDER.value

    if _has_any(low, "пинг", "напиши мне", "присылай мне"):
        return AgentRole.PERSONAL_REMINDER.value

    if _has_any(low, "команд", "/") and _has_any(low, "бот", "личк", "max"):
        return AgentRole.DM_ASSISTANT.value

    return None


def _extract_quoted_reminder_text(clean: str) -> str | None:
    for match in _QUOTED_TEXT_RE.finditer(clean):
        for group in match.groups():
            if group and group.strip():
                return group.strip()
    m = re.search(r'текст\s+напоминан\w*\s+(\S+)', clean, re.I)
    if m:
        return m.group(1).strip('"«»')
    return None


def user_wants_today_run(text: str) -> bool:
    low = (text or "").lower()
    return _has_any(low, "сегодня") and _has_any(
        low, "сделай", "сделать", "отправ", "пришли", "запусти", "выполни", "сработ"
    )


def _normalize_schedule_text(clean: str) -> str | None:
    from app.services.agent.schedule import normalize_schedule_phrase

    low = clean.lower()
    if re.search(r"кажд\w+\s+день", low) or "ежедневно" in low:
        hm = _TIME_ONLY_RE.search(clean)
        if hm:
            return f"каждый день в {int(hm.group(1))}:{hm.group(2)}"
        return "каждый день"

    sched = _SCHEDULE_RE.search(clean)
    if not sched:
        hm = _TIME_ONLY_RE.search(clean)
        if hm and not _has_any(low, "сегодня", "завтра", "через"):
            return f"каждый день в {int(hm.group(1))}:{hm.group(2)}"
        return None

    fragment = sched.group(0).strip()
    normalized = normalize_schedule_phrase(fragment)
    if normalized:
        return normalized

    if _has_any(fragment.lower(), "сегодня", "завтра"):
        hm = _TIME_ONLY_RE.search(clean)
        if hm:
            day = "сегодня" if "сегодня" in fragment.lower() else "завтра"
            return f"{day} в {int(hm.group(1))}:{hm.group(2)}"
        return None

    return fragment


def infer_checklist_fields(text: str, data: dict[str, Any]) -> dict[str, Any]:
    """Дополняет чеклист полями из текста пользователя."""
    clean = (text or "").strip()
    if not clean:
        return data

    low = clean.lower()

    if user_corrects_understanding(clean):
        if _is_personal_max_chat(low):
            data["role"] = AgentRole.PERSONAL_REMINDER.value
        prev_msg = data.get("reminder_message") or ""
        if prev_msg and ("?" in prev_msg or _has_any(prev_msg.lower(), "можешь", "можно ли", "напоминание в")):
            data["reminder_message"] = None

    inferred_role = infer_role_from_text(clean)
    if inferred_role:
        data["role"] = inferred_role
    elif not data.get("role"):
        pass

    if user_wants_today_run(clean):
        hm = _TIME_ONLY_RE.search(clean) or _TIME_ONLY_RE.search(str(data.get("schedule_text") or ""))
        if hm:
            data["schedule_text"] = f"сегодня в {int(hm.group(1))}:{hm.group(2)}"
        else:
            data["schedule_text"] = "через 2 минуты"
        if not data.get("timezone"):
            data["timezone"] = DEFAULT_AGENT_TIMEZONE
    else:
        sched_text = _normalize_schedule_text(clean)
        if sched_text:
            data["schedule_text"] = sched_text
            if not data.get("timezone"):
                data["timezone"] = DEFAULT_AGENT_TIMEZONE

    tz = _TZ_RE.search(clean)
    if tz:
        raw = tz.group(0)
        if "москв" in raw.lower() or raw.lower() == "msk":
            data["timezone"] = DEFAULT_AGENT_TIMEZONE
        else:
            data["timezone"] = raw.replace(" ", "")

    quoted = _extract_quoted_reminder_text(clean)
    if quoted:
        data["reminder_message"] = quoted

    role = data.get("role")

    if role == AgentRole.NEWS_DIGEST.value and not data.get("search_topic"):
        if len(clean) > 12 and not quoted:
            data["search_topic"] = clean[:200]

    if role == AgentRole.IMAGE_POST.value and not data.get("image_prompt"):
        if len(clean) > 12:
            data["image_prompt"] = clean[:500]

    if role == AgentRole.DM_ASSISTANT.value:
        if _is_user_group(low):
            data["scope"] = "group"
        elif _is_personal_max_chat(low) or _has_any(low, "личк", "личн", "диалог"):
            data["scope"] = "dm"
        elif _has_any(low, "и личк", "и в личк", "оба", "везде"):
            data["scope"] = "both"

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
        msg = data.get("reminder_message") or ""
        if msg:
            from app.services.agent.generate_content import wants_llm_generated_content

            if wants_llm_generated_content(msg):
                data["content_pipeline"] = "llm_generate"
            elif not data.get("content_pipeline"):
                data["content_pipeline"] = "static"
        if quoted:
            pass
        elif _has_any(low, "текст напоминан") and not data.get("reminder_message"):
            tail = re.split(r"текст\s+напоминан\w*", clean, maxsplit=1, flags=re.I)
            if len(tail) > 1 and tail[1].strip():
                data["reminder_message"] = tail[1].strip().strip('"«»')[:500]

    if role == AgentRole.GROUP_MODERATION.value:
        if _has_any(low, "ссылк", "url", "http"):
            data["moderation_block_links"] = True
        words = re.findall(r"[а-яёa-z]{4,}", low)
        stop = [w for w in words if w in {"спам", "реклама", "мат", "ругательств"}]
        if stop and not data.get("moderation_stop_words"):
            data["moderation_stop_words"] = ", ".join(stop)

    if data.get("schedule_text") and not data.get("timezone"):
        data["timezone"] = DEFAULT_AGENT_TIMEZONE

    return data
