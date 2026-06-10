"""LLM-диалог настройки агента с JSON-чеклистом."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.message import Message, MessageRole
from app.models.user import User
from app.services.agent.capabilities import (
    apply_message_hints,
    build_parse_fallback_reply,
    compose_feasibility_reply,
    reply_looks_like_capabilities_template,
    user_asks_capabilities,
    user_asks_feasibility,
    user_needs_clarification,
    user_wants_continue,
)
from app.services.agent.intent_hints import DEFAULT_AGENT_TIMEZONE
from app.services.agent.constants import CANCEL_PHRASES, SUPPORTED_ROLE_LABELS
from app.services.agent.onboarding import validate_activation
from app.services.agent.schedule import is_schedule_parseable, normalize_schedule_phrase
from app.services.agent.profile import (
    EVENT_DRIVEN_ROLES,
    GROUP_ROLES,
    SCHEDULED_ROLES,
    VALID_ROLES,
    normalize_dm_command,
)
from app.services.providers.factory import resolve_runtime_providers

logger = logging.getLogger(__name__)

CONFIRM_PHRASES = (
    "да",
    "подтверждаю",
    "всё верно",
    "все верно",
    "запускай",
    "активируй",
    "согласен",
    "согласна",
    "ок",
    "okay",
    "верно",
)

AGENT_SYSTEM_PROMPT = """Ты — ассистент настройки агента Glosix для мессенджера MAX.
Веди живой диалог на русском. Отвечай только валидным JSON (без markdown-обёртки).

Что доступно в MAX (внутренняя модель — НЕ озвучивай списком без запроса):
• Личный чат: уведомления, новости по теме, картинки, команды боту.
• Группа (бот — админ): сообщения, картинки, сводки, модерация (удаление по правилам).
• Расписание или команда в личке (для dm_assistant).

Внутренние role (определи сам по запросу):
- personal_reminder — текст в личку по расписанию
- group_reminder — текст в группу по расписанию
- group_message_log — сводка сообщений группы в личку (LLM) по расписанию
- news_digest — поиск новостей по теме + пост в MAX (личка или группа: delivery_mode). Может быть текст + 1–3 фото (content_pipeline=web_digest_images)
- image_post — только генерация картинки по промпту (личка или группа), без новостного текста
- group_moderation — удаление сообщений в группе по правилам (стоп-слова, ссылки)
- dm_assistant — интерактивный помощник: личка и/или группа, vision (фото/OCR/перевод), база знаний из документов

Чеклист (сохраняй заполненное из current_checklist):
- role — см. выше
- schedule_text — для scheduled-ролей (не для dm_assistant / group_moderation)
- timezone — только если пользователь сам назвал пояс; иначе Europe/Moscow (не спрашивай)
- reminder_message — текст сообщения ИЛИ инструкция для генерации (напр. «напиши стишок на 4 строки»)
- content_pipeline: static | llm_generate | web_digest | web_digest_images — static/llm_generate для напоминаний; web_digest — новости текстом; web_digest_images — новостной пост 500–1000 символов + 1–3 иллюстрации
- search_topic — тема для news_digest или dm_assistant с веб-сводкой
- post_min_chars / post_max_chars — длина новостного поста (по умолчанию 500–1000)
- post_image_count_min / post_image_count_max — число фото в посте (1–3)
- image_prompt — описание картинки для image_post / dm_assistant
- dm_command — команда без слэша, напр. news (dm_assistant, если interaction_mode command/both)
- scope: dm | group | both — где слушать (dm_assistant): личка, группа или оба
- interaction_mode: command | support | both — command: только по команде; support: на все сообщения; both: и поддержка, и команда
- support_instructions — как отвечать в режиме поддержки (тон, правила, FAQ-логика). Можно взять из reminder_message
- delivery_mode: dm | group — куда отправлять (news_digest, image_post)
- max_chat_id — ID группы
- bot_is_group_admin / bot_can_read_messages — для групп Glosix при активации сам проверяет через MAX API
  (GET /chats/{chatId}/members, поля is_admin/is_owner у бота). Не спрашивай «бот админ?», если chat_id уже известен —
  оставь null; сервер проверит. Спрашивай только если проверка недоступна (бот не в группе / нет прав на members).
- moderation_stop_words — через запятую (group_moderation)
- moderation_block_links: true/false

Правила диалога:
- Принимай задачу своими словами. НЕ заставляй выбирать из списка и НЕ называй «whitelist».
- Как только пользователь описал задачу — СРАЗУ заполни role и все уже понятные поля в checklist. Не переспрашивай то, что уже сказано.
- НЕ повторяй один и тот же вопрос дважды подряд. Смотри history и current_checklist.
- Живой диалог: reply всегда своими словами, как человек. ЗАПРЕЩЕНО вставлять фиксированный список возможностей или шаблонный блок.
- «Что умеешь» (без конкретной задачи) — кратко своими словами 3–4 примера, попроси описать задачу.
- «Ты можешь сделать X?» / «можно ли Y?» — ответь по существу: **да или нет**, почему; если да — заполни role в checklist и задай ОДИН уточняющий вопрос (расписание, текст, группа). Не подменяй ответ списком всех возможностей. ЗАПРЕЩЕНО отвечать шаблоном «Сейчас агент Glosix в MAX умеет: • …».
- «Твоей группе» / «твоём чате» в обращении к боту = личный диалог с Glosix в MAX (personal_reminder), НЕ группа пользователей.
- Часовой пояс: по умолчанию Europe/Moscow. НЕ спрашивай timezone, если пользователь не указал другой.
- Короткие «ок», «продолжим», «дальше» — объясни ОДИН следующий шаг по missing_fields, не начинай диалог заново.

Примеры (пользователь → role + поля):
- «напоминай каждый день в 9 про встречу» → personal_reminder, schedule_text, reminder_message, content_pipeline=static
- «через 2 минуты напиши стишок на 4 строки» → personal_reminder, schedule_text, reminder_message=инструкция, content_pipeline=llm_generate (НЕ дословная цитата инструкции в MAX)
- «пиши в группу каждый вечер итог дня» → group_reminder или group_message_log
- «новости про ИИ каждое утро» → news_digest, search_topic, schedule_text
- «публикуй в группу -ID новости про ИИ раз в час: текст 500–1000 символов, 1–3 фото» → news_digest, delivery_mode=group, max_chat_id, search_topic, schedule_text=каждый час, content_pipeline=web_digest_images, post_min_chars=500, post_max_chars=1000, post_image_count_min=1, post_image_count_max=3
- «раз в час» / «каждый час» / «every hour» → schedule_text=каждый час (НЕ переспрашивай расписание)
- «отвечай в группе на вопросы, переводи текст с фото» → dm_assistant, scope=group, interaction_mode=support
- «удаляй спам и ссылки в группе» → group_moderation, moderation_stop_words/block_links
- «ты можешь сделать напоминание в личке?» → reply: да; role=personal_reminder; спроси когда и о чём
- «напиши в группу "Привет"» + ссылка max.ru/-ID + «прямо сейчас» → group_reminder, max_chat_id, reminder_message, schedule_text=через 2 минуты, bot_is_group_admin=true если пользователь сказал что бот админ; ready_for_confirmation если всё заполнено
- Различай «нужно настроить» и «не поддерживается»:
  • Нужно настроить — помоги пошагово, не отказывай: бот не админ в группе (как добавить в админы),
    нет права читать сообщения (как включить), не привязан MAX, не хватает ID группы, расписания,
    часового пояса или текста. Это часть настройки, а не отказ.
  • Не поддерживается — только если запрос принципиально вне MAX: Telegram/WhatsApp/email/CRM,
    сторонние API, вебхуки не в MAX. Ответь по-человечески: «интеграция с … пока не поддерживается»
    или «это за пределами MAX, сейчас не могу». Без списка сценариев.
- Если пользователь не понял («не понял», «не совсем понял», «поясни», «что дальше») —
  НЕ сбрасывай диалог; переформулируй последний шаг проще, опираясь на current_checklist.
  Объясняй один следующий шаг, не сваливай все вопросы разом.
- Задавай по одному недостающему параметру за раз (кроме случая, когда пользователь сам дал всё сразу).
- Для dm_assistant с группой: бот должен быть админом (bot_is_group_admin). Vision: пользователь может прислать фото с текстом «переведи с картинки».
- База знаний: пользователь может прикрепить txt/pdf/docx в этот тред — сообщи, что документ можно загрузить кнопкой «+».
- Если max_linked=false — объясни привязку MAX (Профиль → войти через MAX). Не активируй агента.
- Когда обязательные поля заполнены: ready_for_confirmation=true и confirmation_summary с итогом.
- activate=true только при явном подтверждении (да/подтверждаю) И max_linked=true.
- reply — текст пользователю (можно markdown), без дублирования JSON.

Формат ответа:
{
  "reply": "текст",
    "checklist": {
    "role": null,
    "schedule_text": null,
    "timezone": null,
    "reminder_message": null,
    "search_topic": null,
    "image_prompt": null,
    "dm_command": null,
    "scope": null,
    "interaction_mode": null,
    "support_instructions": null,
    "delivery_mode": null,
    "max_chat_id": null,
    "bot_is_group_admin": null,
    "bot_can_read_messages": null,
    "moderation_stop_words": null,
    "moderation_block_links": null
  },
  "ready_for_confirmation": false,
  "confirmation_summary": null,
  "activate": false
}
"""


@dataclass
class ChecklistState:
    role: str | None = None
    schedule_text: str | None = None
    timezone: str | None = None
    reminder_message: str | None = None
    search_topic: str | None = None
    image_prompt: str | None = None
    dm_command: str | None = None
    scope: str | None = None
    interaction_mode: str | None = None
    support_instructions: str | None = None
    delivery_mode: str | None = None
    max_chat_id: int | None = None
    bot_is_group_admin: bool | None = None
    bot_can_read_messages: bool | None = None
    moderation_stop_words: str | None = None
    moderation_block_links: bool | None = None
    content_pipeline: str | None = None
    post_min_chars: int | None = None
    post_max_chars: int | None = None
    post_image_count_min: int | None = None
    post_image_count_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "schedule_text": self.schedule_text,
            "timezone": self.timezone,
            "reminder_message": self.reminder_message,
            "search_topic": self.search_topic,
            "image_prompt": self.image_prompt,
            "dm_command": self.dm_command,
            "scope": self.scope,
            "interaction_mode": self.interaction_mode,
            "support_instructions": self.support_instructions,
            "delivery_mode": self.delivery_mode,
            "max_chat_id": self.max_chat_id,
            "bot_is_group_admin": self.bot_is_group_admin,
            "bot_can_read_messages": self.bot_can_read_messages,
            "moderation_stop_words": self.moderation_stop_words,
            "moderation_block_links": self.moderation_block_links,
            "content_pipeline": self.content_pipeline,
            "post_min_chars": self.post_min_chars,
            "post_max_chars": self.post_max_chars,
            "post_image_count_min": self.post_image_count_min,
            "post_image_count_max": self.post_image_count_max,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChecklistState:
        raw = raw or {}
        chat_raw = raw.get("max_chat_id")
        chat_id: int | None = None
        if isinstance(chat_raw, int):
            chat_id = chat_raw
        elif isinstance(chat_raw, str) and chat_raw.lstrip("-").isdigit():
            chat_id = int(chat_raw)
        role = raw.get("role")
        if role not in VALID_ROLES:
            role = None
        dm = _str_or_none(raw.get("dm_command"))
        if dm:
            dm = normalize_dm_command(dm)
        delivery = _str_or_none(raw.get("delivery_mode"))
        if delivery:
            delivery = delivery.lower()
            if delivery not in {"dm", "group"}:
                delivery = None
        scope = _str_or_none(raw.get("scope"))
        if scope:
            scope = scope.lower()
            if scope not in {"dm", "group", "both"}:
                scope = None
        mode = _str_or_none(raw.get("interaction_mode"))
        if mode:
            mode = mode.lower()
            if mode not in {"command", "support", "both"}:
                mode = None
        schedule_text = _str_or_none(raw.get("schedule_text"))
        timezone = _str_or_none(raw.get("timezone"))
        if schedule_text and not timezone:
            timezone = DEFAULT_AGENT_TIMEZONE
        return cls(
            role=role,
            schedule_text=schedule_text,
            timezone=timezone,
            reminder_message=_str_or_none(raw.get("reminder_message")),
            search_topic=_str_or_none(raw.get("search_topic")),
            image_prompt=_str_or_none(raw.get("image_prompt")),
            dm_command=dm,
            scope=scope,
            interaction_mode=mode,
            support_instructions=_str_or_none(raw.get("support_instructions")),
            delivery_mode=delivery,
            max_chat_id=chat_id,
            bot_is_group_admin=_bool_or_none(raw.get("bot_is_group_admin")),
            bot_can_read_messages=_bool_or_none(raw.get("bot_can_read_messages")),
            moderation_stop_words=_str_or_none(raw.get("moderation_stop_words")),
            moderation_block_links=_bool_or_none(raw.get("moderation_block_links")),
            content_pipeline=_str_or_none(raw.get("content_pipeline")),
            post_min_chars=_int_or_none(raw.get("post_min_chars")),
            post_max_chars=_int_or_none(raw.get("post_max_chars")),
            post_image_count_min=_int_or_none(raw.get("post_image_count_min")),
            post_image_count_max=_int_or_none(raw.get("post_image_count_max")),
        )


@dataclass
class LlmTurnResult:
    reply: str
    checklist: ChecklistState
    ready_for_confirmation: bool = False
    confirmation_summary: str | None = None
    activate: bool = False


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "да", "yes", "1"}:
            return True
        if low in {"false", "нет", "no", "0"}:
            return False
    return None


def user_wants_cancel(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(phrase in low for phrase in CANCEL_PHRASES)


def user_wants_confirm(text: str) -> bool:
    low = (text or "").strip().lower()
    if low in CONFIRM_PHRASES:
        return True
    return any(low.startswith(p + " ") or low.endswith(" " + p) for p in ("да", "подтверждаю", "согласен"))


def load_checklist(agent: AgentInstance) -> ChecklistState:
    cfg = dict(agent.config or {})
    stored = cfg.get("checklist")
    if isinstance(stored, dict):
        return ChecklistState.from_dict(stored)
    return ChecklistState.from_dict(
        {
            "role": agent.role,
            "schedule_text": cfg.get("schedule_text"),
            "timezone": cfg.get("timezone"),
            "reminder_message": cfg.get("reminder_message"),
            "search_topic": cfg.get("search_topic"),
            "image_prompt": cfg.get("image_prompt"),
            "dm_command": cfg.get("dm_command"),
            "scope": cfg.get("scope"),
            "interaction_mode": cfg.get("interaction_mode"),
            "support_instructions": cfg.get("support_instructions"),
            "delivery_mode": cfg.get("delivery_mode"),
            "max_chat_id": agent.max_chat_id or cfg.get("max_chat_id"),
            "bot_is_group_admin": cfg.get("bot_is_group_admin"),
            "bot_can_read_messages": cfg.get("bot_can_read_messages"),
            "moderation_stop_words": cfg.get("moderation_stop_words"),
            "moderation_block_links": cfg.get("moderation_block_links"),
        }
    )


_CHECKLIST_CORE_FIELDS = frozenset(
    {
        "role",
        "schedule_text",
        "timezone",
        "reminder_message",
        "search_topic",
        "image_prompt",
        "dm_command",
        "scope",
        "interaction_mode",
        "support_instructions",
        "delivery_mode",
        "max_chat_id",
    }
)


def _schedule_has_recurrence(text: str) -> bool:
    low = (text or "").lower()
    return any(
        token in low
        for token in (
            "кажд",
            "ежеднев",
            "еженедел",
            "понедельник",
            "вторник",
            "сред",
            "четверг",
            "пятниц",
            "суббот",
            "воскресен",
            "час",
            "hour",
            "hourly",
        )
    )


def _is_weaker_schedule(new: str | None, old: str | None) -> bool:
    if not new or not old:
        return False
    new_low = new.lower().strip()
    old_low = old.lower().strip()
    if new_low == old_low:
        return False
    if _schedule_has_recurrence(old_low) and not _schedule_has_recurrence(new_low):
        if any(token in new_low for token in ("сегодня", "завтра")):
            return True
    if re.search(r"\d{1,2}[:.]\d{2}", old_low) and new_low in {"сегодня", "завтра"}:
        return True
    if is_schedule_parseable(old_low) and not is_schedule_parseable(new_low):
        return True
    return False


def merge_checklist(
    current: ChecklistState,
    patch: ChecklistState,
    *,
    user_text: str = "",
) -> ChecklistState:
    data = current.to_dict()
    lock_core = user_wants_confirm(user_text) and bool(data.get("role"))
    for key, value in patch.to_dict().items():
        if value is None:
            continue
        if lock_core and key in _CHECKLIST_CORE_FIELDS:
            continue
        if key == "schedule_text" and _is_weaker_schedule(str(value), data.get("schedule_text")):
            continue
        data[key] = value
    return ChecklistState.from_dict(data)


def enrich_schedule_from_history(
    checklist: ChecklistState,
    history: list[dict[str, str]],
) -> ChecklistState:
    from app.services.agent.intent_hints import user_wants_today_run

    data = checklist.to_dict()
    sched = str(data.get("schedule_text") or "")
    tz = data.get("timezone")
    last_user = next((m.get("text") or "" for m in reversed(history) if m.get("role") == "user"), "")
    if user_wants_today_run(last_user):
        return checklist
    needs_better = not sched or not is_schedule_parseable(sched, tz)
    if not needs_better:
        return checklist

    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        trial = apply_message_hints({}, msg.get("text") or "")
        candidate = trial.get("schedule_text")
        if not candidate:
            continue
        normalized = normalize_schedule_phrase(str(candidate)) or str(candidate)
        if is_schedule_parseable(normalized, tz):
            if _schedule_has_recurrence(normalized) or not sched:
                data["schedule_text"] = normalized
                return ChecklistState.from_dict(data)
    return checklist


def finalize_checklist(
    checklist: ChecklistState,
    *,
    history: list[dict[str, str]] | None = None,
) -> ChecklistState:
    data = checklist.to_dict()
    sched = data.get("schedule_text")
    if sched:
        normalized = normalize_schedule_phrase(str(sched))
        if normalized:
            data["schedule_text"] = normalized
    checklist = ChecklistState.from_dict(data)
    if history:
        checklist = enrich_schedule_from_history(checklist, history)
    return checklist


def apply_checklist_to_agent(agent: AgentInstance, checklist: ChecklistState) -> None:
    cfg = dict(agent.config or {})
    cfg["checklist"] = checklist.to_dict()
    cfg["schedule_text"] = checklist.schedule_text
    cfg["timezone"] = checklist.timezone or cfg.get("timezone") or "Europe/Moscow"
    cfg["reminder_message"] = checklist.reminder_message
    if checklist.role in {
        AgentRole.PERSONAL_REMINDER.value,
        AgentRole.GROUP_REMINDER.value,
    }:
        from app.services.agent.generate_content import (
            generation_instruction,
            wants_llm_generated_content,
        )

        msg = checklist.reminder_message or ""
        if wants_llm_generated_content(msg):
            cfg["content_pipeline"] = "llm_generate"
            cfg["generation_prompt"] = generation_instruction(msg)
        else:
            cfg["content_pipeline"] = "static"
            cfg.pop("generation_prompt", None)
    cfg["search_topic"] = checklist.search_topic
    cfg["image_prompt"] = checklist.image_prompt
    cfg["dm_command"] = checklist.dm_command
    if checklist.scope:
        cfg["scope"] = checklist.scope
    if checklist.interaction_mode:
        cfg["interaction_mode"] = checklist.interaction_mode
    if checklist.support_instructions:
        cfg["support_instructions"] = checklist.support_instructions
    if checklist.delivery_mode:
        cfg["delivery_mode"] = checklist.delivery_mode
    cfg["bot_is_group_admin"] = checklist.bot_is_group_admin
    cfg["bot_can_read_messages"] = checklist.bot_can_read_messages
    if checklist.moderation_stop_words:
        cfg["moderation_stop_words"] = checklist.moderation_stop_words
        rules = dict(cfg.get("moderation_rules") or {})
        rules["stop_words"] = [
            w.strip().lower()
            for w in checklist.moderation_stop_words.split(",")
            if w.strip()
        ]
        cfg["moderation_rules"] = rules
    if checklist.moderation_block_links is not None:
        cfg["moderation_block_links"] = checklist.moderation_block_links
        rules = dict(cfg.get("moderation_rules") or {})
        rules["block_links"] = checklist.moderation_block_links
        cfg["moderation_rules"] = rules
    if checklist.content_pipeline:
        cfg["content_pipeline"] = checklist.content_pipeline
    if checklist.post_min_chars is not None:
        cfg["post_min_chars"] = checklist.post_min_chars
    if checklist.post_max_chars is not None:
        cfg["post_max_chars"] = checklist.post_max_chars
    if checklist.post_image_count_min is not None:
        cfg["post_image_count_min"] = checklist.post_image_count_min
    if checklist.post_image_count_max is not None:
        cfg["post_image_count_max"] = checklist.post_image_count_max
    if checklist.max_chat_id is not None:
        cfg["max_chat_id"] = checklist.max_chat_id
        agent.max_chat_id = checklist.max_chat_id
    elif cfg.get("registered_group_chat_id") and not agent.max_chat_id:
        agent.max_chat_id = int(cfg["registered_group_chat_id"])
        checklist.max_chat_id = agent.max_chat_id
        cfg["max_chat_id"] = agent.max_chat_id
        cfg["checklist"] = checklist.to_dict()

    if checklist.role:
        agent.role = checklist.role
    agent.config = cfg
    if checklist.schedule_text or checklist.reminder_message:
        parts = [p for p in (checklist.schedule_text, checklist.reminder_message) if p]
        agent.instruction_text = " | ".join(parts)


def checklist_missing_fields(checklist: ChecklistState) -> list[str]:
    missing: list[str] = []
    role = checklist.role
    if not role:
        missing.append("role")
        return missing

    if role in SCHEDULED_ROLES:
        if not checklist.schedule_text:
            missing.append("schedule")
        elif not is_schedule_parseable(
            checklist.schedule_text,
            checklist.timezone,
        ):
            missing.append("schedule")

    if role == AgentRole.NEWS_DIGEST.value:
        if not (checklist.search_topic or checklist.reminder_message):
            missing.append("search_topic")
    elif role == AgentRole.IMAGE_POST.value:
        if not (checklist.image_prompt or checklist.reminder_message):
            missing.append("image_prompt")
    elif role == AgentRole.DM_ASSISTANT.value:
        mode = (checklist.interaction_mode or "command").lower()
        scope = (checklist.scope or "dm").lower()
        if mode in {"command", "both"} and not normalize_dm_command(checklist.dm_command):
            missing.append("dm_command")
        if mode in {"support", "both"} and not (
            checklist.support_instructions or checklist.reminder_message
        ):
            missing.append("support_instructions")
        if mode == "command" and not (
            checklist.reminder_message
            or checklist.search_topic
            or checklist.image_prompt
            or checklist.support_instructions
        ):
            missing.append("dm_action")
        if scope in {"group", "both"}:
            if not checklist.max_chat_id:
                missing.append("group_chat")
            if checklist.bot_is_group_admin is not True:
                missing.append("bot_admin")
    elif role == AgentRole.GROUP_MODERATION.value:
        if not checklist.moderation_stop_words and checklist.moderation_block_links is not True:
            missing.append("moderation_rules")
    elif not checklist.reminder_message:
        missing.append("message")

    needs_group = role in GROUP_ROLES or (
        role in {AgentRole.NEWS_DIGEST.value, AgentRole.IMAGE_POST.value}
        and (checklist.delivery_mode or "dm") == "group"
    )
    if needs_group:
        if not checklist.max_chat_id:
            missing.append("group_chat")
        if checklist.bot_is_group_admin is not True:
            missing.append("bot_admin")
        if role == AgentRole.GROUP_MESSAGE_LOG.value and checklist.bot_can_read_messages is not True:
            missing.append("bot_read")
    return missing


def _sanitize_agent_reply(reply: str, user_text: str, checklist: ChecklistState) -> str:
    if reply_looks_like_capabilities_template(reply):
        fallback = compose_feasibility_reply(checklist.to_dict(), user_text)
        if fallback:
            return fallback
        return build_parse_fallback_reply(checklist.to_dict(), user_text)
    return reply


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("{")
    if start < 0:
        return None
    for end in range(len(text), start, -1):
        if text[end - 1] != "}":
            continue
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _history_messages(messages: list[Message]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in sorted(messages, key=lambda x: x.created_at):
        if m.role == MessageRole.USER:
            out.append({"role": "user", "text": m.content})
        elif m.role == MessageRole.ASSISTANT:
            out.append({"role": "assistant", "text": m.content})
    return out


def _context_block(
    user: User,
    agent: AgentInstance,
    checklist: ChecklistState,
    last_user_text: str = "",
) -> str:
    cfg = dict(agent.config or {})
    registered = cfg.get("registered_group_chat_id")
    missing = checklist_missing_fields(checklist)
    lines = [
        f"max_linked: {bool(user.max_user_id)}",
        f"max_user_id: {user.max_user_id or 'нет'}",
        f"agent_status: {agent.status}",
        f"registered_group_chat_id: {registered or 'нет'}",
        f"knowledge_chunks: {cfg.get('knowledge_chunk_count') or 0}",
        f"knowledge_sources: {', '.join(cfg.get('knowledge_sources') or []) or 'нет'}",
        f"current_checklist: {json.dumps(checklist.to_dict(), ensure_ascii=False)}",
        f"missing_fields: {', '.join(missing) if missing else 'нет'}",
        "default_timezone: Europe/Moscow",
    ]
    if user_needs_clarification(last_user_text):
        lines.append(
            "user_signal: needs_clarification — переформулируй последний шаг проще, "
            "сохрани current_checklist, не начинай диалог заново"
        )
    if user_asks_feasibility(last_user_text):
        lines.append(
            "user_signal: asks_feasibility — ответь да/нет по существу; если да, заполни role и задай один уточняющий вопрос; без списка всех возможностей"
        )
    elif user_asks_capabilities(last_user_text):
        lines.append(
            "user_signal: asks_capabilities — кратко своими словами 3–4 примера, попроси описать задачу"
        )
    if user_wants_continue(last_user_text):
        lines.append(
            "user_signal: wants_continue — один конкретный следующий шаг по missing_fields, без сброса"
        )
    return "\n".join(lines)


async def run_llm_turn(
    db,
    redis_client,
    user: User,
    agent: AgentInstance,
    messages: list[Message],
) -> LlmTurnResult:
    checklist = load_checklist(agent)
    history = _history_messages(messages)
    last_user = history[-1]["text"] if history and history[-1]["role"] == "user" else ""
    if not history or history[-1]["role"] != "user":
        logger.warning("Agent LLM turn without trailing user message")

    checklist = ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user))

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)

    payload_messages: list[dict[str, str]] = [
        {"role": "system", "text": AGENT_SYSTEM_PROMPT},
        {"role": "system", "text": _context_block(user, agent, checklist, last_user)},
        *history,
    ]

    raw = ""
    try:
        if hasattr(llm, "complete_text"):
            raw = await llm.complete_text(  # type: ignore[attr-defined]
                payload_messages, model="pro", max_tokens=900, temperature=0.3
            )
        else:
            raise AttributeError("complete_text unavailable")
    except Exception as exc:
        logger.exception("Agent LLM complete_text failed: %s", exc)
        fallback_checklist = finalize_checklist(
            ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user)),
            history=history,
        )
        return LlmTurnResult(
            reply=build_parse_fallback_reply(fallback_checklist.to_dict(), last_user),
            checklist=fallback_checklist,
        )

    data = _parse_llm_json(raw)
    if not data:
        logger.warning("Agent LLM JSON parse failed, retrying: %s", raw[:300])
        try:
            retry_messages = [
                *payload_messages,
                {
                    "role": "system",
                    "text": "Предыдущий ответ не был валидным JSON. Ответь снова — только JSON-объект по схеме.",
                },
            ]
            raw = await llm.complete_text(  # type: ignore[attr-defined]
                retry_messages, model="pro", max_tokens=900, temperature=0.2
            )
            data = _parse_llm_json(raw)
        except Exception:
            data = None

    if not data:
        logger.warning("Agent LLM JSON parse failed after retry: %s", raw[:300])
        fallback_checklist = finalize_checklist(
            ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user)),
            history=history,
        )
        return LlmTurnResult(
            reply=build_parse_fallback_reply(fallback_checklist.to_dict(), last_user),
            checklist=fallback_checklist,
        )

    patch = ChecklistState.from_dict(data.get("checklist") if isinstance(data.get("checklist"), dict) else {})
    merged = merge_checklist(checklist, patch, user_text=last_user)
    merged = ChecklistState.from_dict(apply_message_hints(merged.to_dict(), last_user))
    merged = finalize_checklist(merged, history=history)
    reply = _sanitize_agent_reply(
        _str_or_none(data.get("reply")) or build_parse_fallback_reply(merged.to_dict(), last_user),
        last_user,
        merged,
    )
    ready = bool(data.get("ready_for_confirmation"))
    summary = _str_or_none(data.get("confirmation_summary"))
    activate = bool(data.get("activate"))

    if not user.max_user_id:
        activate = False
        if "max_linked" not in reply.lower() and "привяз" not in reply.lower():
            reply += (
                "\n\nСначала привяжите MAX: откройте **Профиль** в Glosix и войдите через MAX "
                "(или привяжите существующий аккаунт)."
            )

    missing = checklist_missing_fields(merged)
    if user_wants_confirm(last_user) and not missing:
        activate = True
        ready = True
    else:
        from app.services.agent.intent_hints import user_wants_immediate_run, user_wants_today_run

        if (user_wants_today_run(last_user) or user_wants_immediate_run(last_user)) and not missing:
            activate = True
            ready = True

    if activate and missing:
        activate = False
        reply = build_parse_fallback_reply(merged.to_dict(), last_user)

    return LlmTurnResult(
        reply=reply,
        checklist=merged,
        ready_for_confirmation=ready,
        confirmation_summary=summary,
        activate=activate and bool(user.max_user_id),
    )


def build_confirmation_prompt(summary: str | None, checklist: ChecklistState) -> str:
    if summary:
        return f"{summary}\n\nЗапустить агента? Ответьте «да» или «подтверждаю»."
    role_label = SUPPORTED_ROLE_LABELS.get(checklist.role or "", checklist.role or "—")
    lines = [
        "Проверьте настройки перед запуском:",
        f"• Задача: {role_label}",
    ]
    if checklist.schedule_text:
        lines.append(f"• Расписание: {checklist.schedule_text}")
        lines.append(f"• Часовой пояс: {checklist.timezone or 'Europe/Moscow'}")
    if checklist.search_topic:
        lines.append(f"• Тема: {checklist.search_topic}")
    if checklist.image_prompt:
        lines.append(f"• Промпт картинки: {checklist.image_prompt}")
    if checklist.dm_command:
        lines.append(f"• Команда в MAX: /{checklist.dm_command}")
    if checklist.scope:
        lines.append(f"• Где работает: {checklist.scope}")
    if checklist.interaction_mode:
        lines.append(f"• Режим: {checklist.interaction_mode}")
    if checklist.support_instructions:
        lines.append(f"• Поддержка: {checklist.support_instructions[:120]}")
    if checklist.reminder_message:
        from app.services.agent.generate_content import wants_llm_generated_content

        if wants_llm_generated_content(checklist.reminder_message):
            lines.append(f"• Контент: генерируется по запросу «{checklist.reminder_message}»")
        else:
            lines.append(f"• Текст: {checklist.reminder_message}")
    if checklist.max_chat_id:
        lines.append(f"• Группа MAX: {checklist.max_chat_id}")
    if checklist.moderation_stop_words or checklist.moderation_block_links:
        lines.append("• Модерация: настроена")
    lines.append("\nЗапустить агента? Ответьте «да» или «подтверждаю».")
    return "\n".join(lines)


def try_validate_checklist(checklist: ChecklistState) -> None:
    class _AgentShim:
        role = checklist.role
        max_chat_id = checklist.max_chat_id
        config = checklist.to_dict()

    validate_activation(_AgentShim())  # type: ignore[arg-type]
