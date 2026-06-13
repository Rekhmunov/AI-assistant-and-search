"""Локальное распознавание намерения пользователя при настройке агента."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentRole

DEFAULT_AGENT_TIMEZONE = "Europe/Moscow"

_SCHEDULE_RE = re.compile(
    r"(кажд\w+\s+(?:день|утр|вечер|недел|понедельник|вторник|сред|четверг|пятниц|суббот|воскресен|час))"
    r"|(?:раз\s+в\s+час|every\s+hour|hourly)"
    r"|(?:завтра|послезавтра|сегодня|через\s+\d+)"
    r"|(?:в\s+)?\d{1,2}[:.]\d{2}"
    r"|(?:в\s+\d{1,2}\s*час)",
    re.I,
)

_HOURLY_SCHEDULE_RE = re.compile(
    r"(?:раз\s+в\s+час|кажд\w+\s+час|every\s+hour|hourly)",
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
            "задачу не давал",
            "задачу не давала",
            "не давал задач",
            "не давала задач",
            "не просил настраивать",
            "не просила настраивать",
            "не просил запускать",
            "никакую задачу",
            "никакую не давал",
            "не давал",
            "не давала",
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
    if _is_personal_max_chat(low):
        return False
    if _has_any(
        low,
        "моей групп",
        "нашей групп",
        "в группе",
        "в группу",
        "эту групп",
        "эта групп",
        "групповой чат",
        "web.max.ru",
        "max.ru/-",
    ):
        return True
    return bool(re.search(r"\bгрупп[уыаеой]", low))


def infer_role_from_text(text: str) -> str | None:
    """Эвристика: определить role по свободной формулировке задачи."""
    from app.services.agent.expense_tracker import is_structured_group_tracker_task
    from app.services.agent.operational import is_operational_max_query

    clean = (text or "").strip()
    low = clean.lower()
    if is_operational_max_query(clean):
        return None

    if is_structured_group_tracker_task(clean):
        return AgentRole.DM_ASSISTANT.value
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

    if _has_any(low, "новост", "дайджест") and not _has_any(low, "сводк сообщ"):
        return AgentRole.NEWS_DIGEST.value

    if _has_any(low, "сгенерир", "генерир", "нарисуй") and _has_any(
        low, "отправ", "присылай", "публик", "пост"
    ):
        if not _has_any(low, "новост", "дайджест"):
            return AgentRole.IMAGE_POST.value

    if _has_any(low, "картинк", "изображен", "фото") and _has_any(
        low, "отправ", "присылай", "публик", "пост"
    ):
        if _has_any(low, "новост", "дайджест", "ии", "искусственн", "нейросет"):
            return AgentRole.NEWS_DIGEST.value
        if not _has_any(low, "сгенерир", "генерир", "нарисуй"):
            return AgentRole.IMAGE_POST.value

    if _has_any(low, "сводк", "итог дня", "резюме") and _has_any(low, "групп", "чат"):
        return AgentRole.GROUP_MESSAGE_LOG.value

    if is_structured_group_tracker_task(clean):
        return AgentRole.DM_ASSISTANT.value

    if _is_user_group(low) and _has_any(low, "сообщ", "пиши", "напис", "отправ", "пост"):
        return AgentRole.GROUP_REMINDER.value

    if _has_any(low, "групп") and _has_any(low, "напиши", "пиши", "напис", "отправ", "пост"):
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


def user_wants_immediate_run(text: str) -> bool:
    """Одноразовый запуск «прямо сейчас», без ожидания подтверждения расписания."""
    low = (text or "").lower()
    if _has_any(
        low,
        "прямо сейчас",
        "сейчас напиши",
        "сейчас отправ",
        "немедленно",
        "сразу напиши",
        "сразу отправ",
        "прямо сейчас напиши",
        "разово",
        "один раз",
        "одноразово",
        "разовое",
        "разовую",
    ):
        return True
    return _has_any(low, "сейчас", "сразу") and _has_any(low, "напиши", "напис", "отправ", "пришли", "пост")


def _extract_post_image_count(low: str) -> tuple[int, int] | None:
    m = re.search(
        r"(?:от\s+)?(\d)\s*(?:до|[-–])\s*(\d)\s*(?:фото|картин|изображен)",
        low,
    )
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d)\s*[-–]\s*(\d)\s*(?:фото|картин|изображен)", low)
    if m:
        return int(m.group(1)), int(m.group(2))
    if _has_any(low, "фото", "картинк", "изображен"):
        return 1, 3
    return None


def _extract_post_length_limits(low: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{3,4})\s*[-–]\s*(\d{3,4})\s*(?:симв|знак|char)", low)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"от\s+(\d{3,4})\s+до\s+(\d{3,4})", low)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _extract_search_topic(clean: str, low: str) -> str | None:
    if _has_any(low, "новост", "дайджест") and (
        _has_any(low, "ии", "искусственн", "нейросет") or re.search(r"\bai\b", low)
    ):
        return "новости искусственного интеллекта"

    m = re.search(r"новост\w*\s+(?:об?|про)\s+([^\n.,;]+)", low, re.I)
    if m:
        topic = m.group(1).strip(" .,;")[:200]
        if topic:
            return topic
    return None


def _normalize_schedule_text(clean: str) -> str | None:
    from app.services.agent.schedule import normalize_schedule_phrase

    low = clean.lower()
    if _HOURLY_SCHEDULE_RE.search(low):
        return "каждый час"

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
    """Извлекает только структурные данные — chat_id. Остальное решает LLM."""
    clean = (text or "").strip()
    if not clean:
        return data
    chat_id = _extract_max_chat_id(clean)
    if chat_id is not None:
        data["max_chat_id"] = chat_id
    return data


def _extract_max_chat_id(text: str) -> int | None:
    for match in re.finditer(r"-?\d{5,}", text or ""):
        try:
            return int(match.group(0))
        except ValueError:
            continue
    return None


def _mentions_admin_in_text(low: str) -> bool:
    return _has_any(low, "админ", "администратор", "admin")


def _denies_admin(low: str) -> bool:
    return _has_any(low, "не админ", "не является", "неявляется", "не администратор")
