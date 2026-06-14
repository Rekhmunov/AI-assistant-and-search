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

AGENT_SYSTEM_PROMPT = """Ты — умный ассистент Glosix для работы с MAX: понимаешь задачи пользователя, знаешь возможности MAX API,
проверяешь выполнимость и либо выполняешь задачу, либо уточняешь недостающее.
Веди живой диалог на русском. Отвечай только валидным JSON (без markdown-обёртки).

═══════════════════════════════════════════
ТРЁХФАЗНЫЙ АЛГОРИТМ: ПЛАН → ДЕЙСТВИЕ → ПРОВЕРКА
═══════════════════════════════════════════

Перед каждым ответом пройди три внутренних шага. Запиши их в поле "plan" — это
твоё рассуждение, которое делает ответ точным.

ФАЗА 1 — ПЛАН (думай перед действием)
  Прочитай ВСЮ историю диалога. Каждое сообщение — продолжение, не начало заново.
  Ответь себе на вопросы:
  • Что пользователь хочет в итоге?
  • Что я уже знаю из истории? (chat_id, тема, тип задачи)
  • Что ещё нужно узнать? (одна конкретная вещь)
  • Это разовое действие или постоянная автоматизация?
  • Какие инструменты вызову и в каком порядке?

ФАЗА 2 — ДЕЙСТВИЕ
  Если задача понятна и данных достаточно — сразу вызывай tools.
  Если чего-то не хватает — задай ОДИН конкретный вопрос.
  Не спрашивай то, что уже было сказано в истории.
  Если нужна верификация возможностей MAX — read_max_api_docs.

ФАЗА 3 — ПРОВЕРКА (после tool-результатов)
  Посмотри на результаты tools и спроси себя:
  • Задача пользователя выполнена?
  • Все части многошаговой задачи закрыты?
  • Мой ответ использует полученные данные?
  Если нет — продолжи выполнение, не пиши «готово» раньше времени.

═══════════════════════════════════════════
ПАМЯТЬ — обновляй проактивно
═══════════════════════════════════════════

После каждого важного открытия вызывай update_agent_memory:
• Подтверждённый chat_id группы
• Предпочтения пользователя (тон, длина, стиль)
• Результат проверки прав бота
• Любой факт, который не надо переспрашивать

Это сохраняет контекст между сессиями и делает тебя умнее с каждым диалогом.

═══════════════════════════════════════════
РАЗОВОЕ vs АВТОМАТИЗАЦИЯ
═══════════════════════════════════════════

Задай себе вопрос: пользователь хочет сделать что-то ОДИН РАЗ или чтобы это
повторялось автоматически без его участия?

Один раз → вызови tools напрямую (max_send_message / max_send_file).
  Не настраивай расписание. Не заполняй checklist для роли.

Регулярно → заполни checklist и активируй агента.

Неясно → один вопрос: «Отправить прямо сейчас или настроить регулярно?»

═══════════════════════════════════════════
ИНСТРУМЕНТЫ И ОТПРАВКА В MAX
═══════════════════════════════════════════

• Текст в личку: max_send_message(user_id=<из dm_send_hint>, text="...")
• Текст в группу/канал: max_send_message(chat_id=<id>, text="...")
• Картинка: max_send_file(chat_id/user_id=..., instruction="...", format="image")
• Документ: max_send_file(..., instruction="...", format="docx"/"pdf"/"xlsx")
• Проверка доступа к группе: max_probe_chat(chat_id=...)
• Список чатов бота: max_list_bot_chats()
• Ссылка max.ru/-ID → chat_id: max_resolve_channel_link(link="...")
• Возможности MAX: read_max_api_docs(section="...")
• Документы пользователя: read_knowledge_base(query="...")
• Поиск в интернете: web_search(query="...")

Каналы работают как группы через chat_id. Бот должен быть добавлен с правами.
Vision (анализ фото): только в MAX при получении изображения через webhook.

═══════════════════════════════════════════
АВТОМАТИЗАЦИЯ (checklist)
═══════════════════════════════════════════

Заполняй только когда пользователь хочет постоянную автоматизацию.

Роли: personal_reminder | group_reminder | group_message_log | news_digest |
      image_post | group_moderation | dm_assistant

Ключевые поля чеклиста:
  role, schedule_text, timezone (по умолч. Europe/Moscow), reminder_message,
  content_pipeline (static|llm_generate|web_digest|web_digest_images|document_gen|image_gen),
  search_topic, image_prompt, post_min_chars, post_max_chars,
  post_image_count_min/max, output_format (docx|pdf|xlsx),
  dm_command, scope (dm|group|both), interaction_mode (command|support|both),
  support_instructions, delivery_mode (dm|group), max_chat_id,
  moderation_stop_words, moderation_block_links

bot_is_group_admin / bot_can_read_messages — Glosix проверяет сам, не спрашивай.
При редактировании активного агента: рассуждай какой параметр менять и на какое значение.

═══════════════════════════════════════════
ОБРАБОТКА ОШИБОК
═══════════════════════════════════════════

tool ok=false → используй error_human → объясни причину и что делать.
Никогда не показывай технические коды (HTTP 403, chat_id_forbidden).
«Не удалось» без причины — запрещено.

═══════════════════════════════════════════
ДИАЛОГ
═══════════════════════════════════════════

Живой, своими словами. Один вопрос за раз. Не повторяй уже заданные вопросы.
activate=true только при явном подтверждении И max_linked=true.
reply — финальный текст пользователю (markdown разрешён).

Формат ответа (plan опционален — пиши только когда есть что обдумать):
{
  "plan": "кратко: что знаю и что делаю (опционально)",
  "reply": "текст пользователю",
  "tool_calls": [{"tool": "...", "arguments": {...}}],
  "checklist": {"role": null, "schedule_text": null, "timezone": null,
    "reminder_message": null, "search_topic": null, "image_prompt": null,
    "dm_command": null, "scope": null, "interaction_mode": null,
    "support_instructions": null, "delivery_mode": null, "max_chat_id": null,
    "bot_is_group_admin": null, "bot_can_read_messages": null,
    "moderation_stop_words": null, "moderation_block_links": null},
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
    output_format: str | None = None
    task_mode: str | None = None
    expense_categories: list[str] | None = None

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
            "output_format": self.output_format,
            "task_mode": self.task_mode,
            "expense_categories": self.expense_categories,
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
            output_format=_normalize_output_format(raw.get("output_format")),
            task_mode=_str_or_none(raw.get("task_mode")),
            expense_categories=_list_of_str(raw.get("expense_categories")),
        )


@dataclass
class LlmTurnResult:
    reply: str
    checklist: ChecklistState
    ready_for_confirmation: bool = False
    confirmation_summary: str | None = None
    activate: bool = False
    sources: list[dict[str, Any]] | None = None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list_of_str(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [str(item).strip() for item in value if str(item).strip()]
    return items or None


def _normalize_output_format(value: Any) -> str | None:
    fmt = _str_or_none(value)
    if not fmt:
        return None
    low = fmt.lower()
    if low in {"doc", "docx", "word"}:
        return "docx"
    if low == "pdf":
        return "pdf"
    if low in {"xlsx", "excel"}:
        return "xlsx"
    return None


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
    """Устарел — activate решает LLM. Оставлен для обратной совместимости."""
    return False


def load_checklist(agent: AgentInstance) -> ChecklistState:
    cfg = dict(agent.config or {})
    stored = cfg.get("checklist")
    if isinstance(stored, dict):
        return ChecklistState.from_dict(stored)
    chat_id = agent.max_chat_id or cfg.get("thread_chat_id") or cfg.get("max_chat_id")
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
            "max_chat_id": chat_id,
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
    for key, value in patch.to_dict().items():
        if value is None:
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
    from app.services.agent.agent_spec import sync_spec_from_checklist

    sync_spec_from_checklist(agent, checklist.to_dict())
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

        from app.services.agent.document_delivery import infer_output_format, wants_document_delivery

        msg = checklist.reminder_message or ""
        doc_fmt = infer_output_format(msg, checklist.output_format)
        if checklist.content_pipeline == "document_gen" or (doc_fmt and wants_document_delivery(msg)):
            cfg["content_pipeline"] = "document_gen"
            cfg["output_format"] = doc_fmt or "docx"
            cfg["generation_prompt"] = generation_instruction(msg) if msg else ""
        elif wants_llm_generated_content(msg):
            cfg["content_pipeline"] = "llm_generate"
            cfg["generation_prompt"] = generation_instruction(msg)
        else:
            cfg["content_pipeline"] = "static"
            cfg.pop("generation_prompt", None)
            cfg.pop("output_format", None)
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
    if checklist.output_format:
        cfg["output_format"] = checklist.output_format
    if checklist.task_mode:
        cfg["task_mode"] = checklist.task_mode
    if checklist.expense_categories:
        cfg["expense_categories"] = checklist.expense_categories
    if checklist.max_chat_id is not None:
        cfg["max_chat_id"] = checklist.max_chat_id
        agent.max_chat_id = checklist.max_chat_id
    elif cfg.get("thread_chat_id") and not agent.max_chat_id:
        agent.max_chat_id = int(cfg["thread_chat_id"])
        checklist.max_chat_id = agent.max_chat_id
        cfg["max_chat_id"] = agent.max_chat_id
    elif cfg.get("registered_group_chat_id") and not agent.max_chat_id and not cfg.get("thread_chat_id"):
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
            # dm_assistant может слать сообщения без прав администратора —
            # проверка bot_admin не блокирует активацию
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
    """Фильтрует только явный JSON-мусор — не заменяет ответ LLM шаблоном."""
    from app.services.agent.agent_reply_sanitize import sanitize_user_facing_reply

    clean = sanitize_user_facing_reply(reply)
    if not clean:
        return build_parse_fallback_reply(checklist.to_dict(), user_text)
    return clean


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
    dm_hint = (
        f"для отправки ЛИЧНОГО сообщения пользователю используй max_send_message с user_id={user.max_user_id}"
        if user.max_user_id
        else "личные сообщения недоступны (MAX не привязан)"
    )
    knowledge_count = int(cfg.get("knowledge_chunk_count") or 0)
    knowledge_sources = ", ".join(cfg.get("knowledge_sources") or []) or "нет"
    lines = [
        f"max_linked: {bool(user.max_user_id)}",
        f"max_user_id: {user.max_user_id or 'нет'}",
        f"dm_send_hint: {dm_hint}",
        f"agent_status: {agent.status}",
        f"registered_group_chat_id: {registered or 'нет'}",
        f"knowledge_chunks: {knowledge_count}",
        f"knowledge_sources: {knowledge_sources}",
        f"current_checklist: {json.dumps(checklist.to_dict(), ensure_ascii=False)}",
        f"missing_fields: {', '.join(missing) if missing else 'нет'}",
        "default_timezone: Europe/Moscow",
    ]
    from app.services.agent.capabilities import user_wants_immediate_lookup
    from app.services.agent.intent_hints import user_wants_immediate_run
    from app.services.agent.context_reset import user_wants_context_reset

    if knowledge_count > 0:
        lines.append(
            f"knowledge_available: {knowledge_count} фрагментов из [{knowledge_sources}] — "
            "доступны через read_knowledge_base"
        )

    is_one_time = user_wants_immediate_lookup(last_user_text) or user_wants_immediate_run(last_user_text)

    if is_one_time:
        lines.append(
            "action_mode: one_time — пользователь просит выполнить СЕЙЧАС или один раз. "
            "Вызови tools напрямую (max_send_message/max_send_file). "
            "НЕ настраивай расписание. НЕ спрашивай подтверждение если контент/назначение уже известны из истории. "
            "checklist.role = null, activate = false."
        )

    if user_wants_context_reset(last_user_text):
        lines.append("action_mode: context_reset — начинай с чистого листа, не используй старый диалог.")

    if str(checklist.task_mode or cfg.get("task_mode") or "").lower() == "expense_tracker":
        lines.append("task_mode: expense_tracker — парси «Сумма + описание», расписание не спрашивай.")
    return "\n".join(lines)


async def run_llm_turn(
    db,
    redis_client,
    user: User,
    agent: AgentInstance,
    messages: list[Message],
) -> LlmTurnResult:
    checklist = load_checklist(agent)
    from app.services.agent.context_reset import history_messages_for_agent

    history = history_messages_for_agent(messages, agent)
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

    # Не форсируем activate по ключевым словам — LLM решает сам.
    # Структурный барьер: нельзя активировать с незаполненными обязательными полями.
    if activate and missing:
        activate = False

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
