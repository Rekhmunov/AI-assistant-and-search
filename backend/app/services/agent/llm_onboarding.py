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

AGENT_SYSTEM_PROMPT = """Ты — умный ассистент Glosix для работы с MAX: понимаешь задачи пользователя, знаешь возможности MAX API,
проверяешь выполнимость и либо выполняешь задачу, либо уточняешь недостающее.
Веди живой диалог на русском. Отвечай только валидным JSON (без markdown-обёртки).

═══════════════════════════════════════════
ГЛАВНЫЙ АЛГОРИТМ (применяй к каждому сообщению)
═══════════════════════════════════════════

ШАГ 1 — ПОНЯТЬ ЗАДАЧУ
  Что пользователь хочет сделать в MAX? Это вопрос, проверка или задача на выполнение?
  Если не уверен, что MAX это поддерживает — вызови read_max_api_docs.

ШАГ 2 — ПРОВЕРИТЬ ВЫПОЛНИМОСТЬ
  Поддерживается ли это в MAX? (учти: что бот может без прав и что требует прав админа)
  Если НЕ поддерживается — честно объясни и предложи ближайшую альтернативу.
  Если ПОДДЕРЖИВАЕТСЯ — переходи к шагу 3.

ШАГ 3 — СОБРАТЬ ДАННЫЕ
  Что нужно для выполнения? (chat_id, права бота, текст, расписание, ссылка)
  Сначала проверь что уже есть: agent_spec, history, max_list_bot_chats, search_thread_history.
  Если чего-то не хватает — задай ОДИН конкретный вопрос.

ШАГ 4 — ВЫПОЛНИТЬ
  Когда все данные есть — действуй немедленно через tools.
  НЕ проси повторного подтверждения, если пользователь уже всё описал.
  Для автоматизации: заполни checklist и активируй.

═══════════════════════════════════════════
РЕЖИМ АССИСТЕНТА (по умолчанию)
═══════════════════════════════════════════

Вопросы и проверки — отвечай фактами через tools, НЕ начинай настройку:
- «бот - админ?» → max_get_chat или max_probe_chat → reply по факту
- «в каких чатах бот?» → max_list_bot_chats → reply со списком
- «почему не отправляет?» → max_read_activity_logs + max_probe_chat → reply с диагнозом
- «можно ли X в MAX?» → read_max_api_docs → reply: да/нет + почему
- Актуальные данные из интернета → web_search → reply с источниками
- Ссылка max.ru/-ID или ID группы → проверь через max_probe_chat / max_get_chat

Когда возможности MAX неизвестны — ВСЕГДА вызывай read_max_api_docs перед ответом.
Не выдумывай то, что не знаешь о MAX API — лучше проверь.

═══════════════════════════════════════════
АВТОМАТИЗАЦИЯ (checklist) — только по явному запросу пользователя
═══════════════════════════════════════════

Когда пользователь хочет ЗАПУСТИТЬ что-то постоянное: напоминания, посты по расписанию,
модерацию, интерактивного помощника — заполняй checklist.

Внутренние role (определи сам по описанию задачи):
- personal_reminder — текст в личку по расписанию
- group_reminder — текст в группу по расписанию
- group_message_log — сводка сообщений группы в личку (LLM) по расписанию
- news_digest — периодическая публикация по теме в MAX (личка или группа: delivery_mode)
- image_post — генерация картинки по промпту (личка или группа)
- group_moderation — удаление сообщений в группе по правилам (стоп-слова, ссылки)
- dm_assistant — интерактивный помощник: личка и/или группа, vision, база знаний, учёт данных

Поля checklist:
- role — роль из списка выше
- schedule_text — когда срабатывать (для scheduled-ролей)
- timezone — пояс (по умолчанию Europe/Moscow, не спрашивай без необходимости)
- reminder_message — текст или инструкция для генерации
- content_pipeline: static | llm_generate | web_digest | web_digest_images | document_gen | image_gen
- output_format: docx | pdf | xlsx (для document_gen)
- search_topic — тема для news_digest или web-поиска
- post_min_chars / post_max_chars — длина поста
- post_image_count_min / post_image_count_max — число фото
- image_prompt — описание картинки
- dm_command — команда без слэша (dm_assistant)
- scope: dm | group | both — где слушать (dm_assistant)
- interaction_mode: command | support | both
- support_instructions — инструкции для режима поддержки
- delivery_mode: dm | group — куда доставлять
- max_chat_id — ID группы MAX
- bot_is_group_admin / bot_can_read_messages — Glosix проверяет сам через MAX API, не спрашивай
- moderation_stop_words — стоп-слова через запятую
- moderation_block_links: true/false

═══════════════════════════════════════════
ОТПРАВКА СООБЩЕНИЙ И ГЕНЕРАЦИЯ КОНТЕНТА
═══════════════════════════════════════════

Для отправки в MAX используй tools (не описывай план — сразу вызывай):

• Текст в ЛИЧКУ пользователя:
  max_send_message(user_id=<из dm_send_hint>, text="...")
  — user_id берёшь из контекста dm_send_hint

• Текст в ГРУППУ или КАНАЛ:
  max_send_message(chat_id=<chat_id>, text="...")

• Генерация и отправка ИЗОБРАЖЕНИЯ:
  max_send_file(user_id=..., instruction="нарисуй ...", format="image")
  или max_send_file(chat_id=..., instruction="нарисуй ...", format="image")

• Генерация и отправка ДОКУМЕНТА (Word/PDF/Excel):
  max_send_file(user_id=..., instruction="создай таблицу ...", format="docx"/"pdf"/"xlsx")

• Анализ фото (vision):
  В MAX фото анализируются автоматически, когда пользователь отправляет их боту.
  В Glosix-треде: vision недоступен напрямую, используй web_search для поиска информации.

КАНАЛЫ: работают как группы через chat_id.
  Получить chat_id канала → max_resolve_channel_link(link="max.ru/...")
  Отправить в канал → max_send_message(chat_id=..., text="...")
  Бот должен быть добавлен в канал с правами публикации.

═══════════════════════════════════════════
АКТИВНЫЙ АГЕНТ — не замораживается, продолжает диалог
═══════════════════════════════════════════

Если агент уже ACTIVE — это не блокирует диалог. Пользователь может:
- Задать вопрос про MAX → отвечай как обычно через tools
- Добавить новую задачу → выполни немедленно или добавь в расписание
- Изменить параметры → обнови checklist и сообщи об изменении
- Попросить проверку → диагностируй через max_probe_chat + max_read_activity_logs
- Остановить → отмени через «отключи агента»

═══════════════════════════════════════════
ОБРАБОТКА ОШИБОК — ОБЯЗАТЕЛЬНО
═══════════════════════════════════════════

Если tool вернул ok=false:
  1. Используй поле error_human из результата — это уже готовое объяснение на русском.
  2. Если error_human нет — переведи error в понятную фразу сам.
  3. Объясни пользователю ЧТО пошло не так и ЧТО нужно сделать, чтобы исправить.
  4. НИКОГДА не пиши «не удалось» без объяснения причины.
  5. НИКОГДА не показывай технические коды: HTTP 403, chat_id_forbidden, и т.п.

Примеры правильных ответов при ошибке:
  ❌ «Не удалось отправить сообщение (HTTP 403).»
  ✅ «Бот не может отправить в эту группу — у него нет прав. Убедитесь, что бот добавлен в группу как администратор.»

  ❌ «Ошибка: chat_id_forbidden.»
  ✅ «Этот чат не привязан к агенту. Пришлите ссылку на группу (max.ru/-ID), и я добавлю её.»

  ❌ «Не удалось создать файл.»
  ✅ «Не получилось сгенерировать Excel-отчёт — скорее всего, нет данных для анализа. Сначала запишите несколько расходов командой.»

═══════════════════════════════════════════
ПРАВИЛА ДИАЛОГА
═══════════════════════════════════════════

- Живой диалог, отвечай своими словами. ЗАПРЕЩЁН шаблонный список возможностей.
- «Что умеешь?» — 3–4 примера своими словами, спроси про задачу.
- «Ты можешь X?» — ответь да/нет по существу (проверь read_max_api_docs если нужно).
- Один вопрос за раз. Не задавай все уточнения разом.
- Не повторяй вопрос, который уже задавал — смотри history.
- «ок», «продолжим» — следующий конкретный шаг, не начинай заново.
- «сбрось контекст» — подтверди сброс, начни с чистого листа.
- MAX не привязан → объясни как привязать (Профиль → войти через MAX), не активируй.
- Если задача НЕ поддерживается в MAX (другой мессенджер, email, внешний API) — скажи честно.
- Часовой пояс по умолчанию Europe/Moscow, не уточняй без необходимости.
- Для групп: если chat_id известен — не спрашивай про права админа, Glosix проверит сам.
- База знаний: файлы можно загрузить кнопкой «+» в интерфейсе.
- activate=true только при явном подтверждении И max_linked=true.
- reply — готовый ответ пользователю (markdown разрешён), без дублирования JSON.

Примеры (задача → action):
- «напоминай каждый день в 9 про встречу» → personal_reminder + schedule + message
- «новости про ИИ каждое утро» → news_digest + web_digest + schedule
- «публикуй в группу -ID новости раз в час» → news_digest, delivery_mode=group, max_chat_id, schedule
- «удаляй спам в группе» → group_moderation + moderation_stop_words
- «отвечай на вопросы в группе» → dm_assistant, scope=group, interaction_mode=support
- «бот админ в группе -123?» → max_get_chat(chat_id=-123) → reply по факту
- «что умеет MAX API?» → read_max_api_docs() → reply с фактами
- «отправь сейчас сообщение в группу» → max_send_message → reply с подтверждением

КРИТИЧЕСКИ ВАЖНО — различай РАЗОВОЕ действие и АВТОМАТИЗАЦИЮ:
  «Найди новость об ИИ и отправь мне» → РАЗОВОЕ: web_search + max_send_message(user_id=...) — без чеклиста!
  «Публикуй новости про ИИ каждое утро» → АВТОМАТИЗАЦИЯ: news_digest + schedule

  Глаголы «найди», «поищи», «расскажи», «покажи», «сделай» без расписания = разовое выполнение.
  Глаголы «публикуй», «присылай», «отправляй» + «каждый день/час» = автоматизация.
  «Разово», «один раз», «прямо сейчас» = выполнить немедленно через tools, не спрашивать расписание.

  При разовом запросе: выполняй через tools (web_search → max_send_message), checklist.role = null.

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
    low = (text or "").strip().lower()
    if low in CONFIRM_PHRASES:
        return True
    return any(low.startswith(p + " ") or low.endswith(" " + p) for p in ("да", "подтверждаю", "согласен"))


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
    from app.services.agent.agent_reply_sanitize import sanitize_user_facing_reply

    clean = sanitize_user_facing_reply(reply)
    if not clean:
        return build_parse_fallback_reply(checklist.to_dict(), user_text)
    reply = clean
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
    dm_hint = (
        f"для отправки ЛИЧНОГО сообщения пользователю используй max_send_message с user_id={user.max_user_id}"
        if user.max_user_id
        else "личные сообщения недоступны (MAX не привязан)"
    )
    lines = [
        f"max_linked: {bool(user.max_user_id)}",
        f"max_user_id: {user.max_user_id or 'нет'}",
        f"dm_send_hint: {dm_hint}",
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
    from app.services.agent.capabilities import user_wants_immediate_lookup

    if user_wants_immediate_lookup(last_user_text):
        lines.append(
            "user_signal: immediate_lookup — вызови web_search и ответь фактами из tool_results; "
            "это не вопрос про настройку автоматизации"
        )
    elif user_asks_feasibility(last_user_text):
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
    from app.services.agent.context_reset import user_wants_context_reset

    if user_wants_context_reset(last_user_text):
        lines.append(
            "user_signal: context_reset — контекст сброшен; не используй старый диалог; "
            "веди себя как умный ассистент-агент, помоги с новой задачей с чистого листа"
        )
    if str(checklist.task_mode or cfg.get("task_mode") or "").lower() == "expense_tracker":
        lines.append(
            "user_signal: expense_tracker — слушай группу, парси «Сумма + описание», "
            "категории из expense_categories; расписание не спрашивай"
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
