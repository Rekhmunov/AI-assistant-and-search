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
    try_local_onboarding_reply,
    user_asks_capabilities,
    user_needs_clarification,
    user_wants_continue,
)
from app.services.agent.constants import CANCEL_PHRASES, SUPPORTED_ROLE_LABELS
from app.services.agent.onboarding import validate_activation
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
- news_digest — поиск новостей по теме + сводка (личка или группа: delivery_mode)
- image_post — генерация картинки по промпту (личка или группа)
- group_moderation — удаление сообщений в группе по правилам (стоп-слова, ссылки)
- dm_assistant — интерактивный помощник: личка и/или группа, vision (фото/OCR/перевод), база знаний из документов

Чеклист (сохраняй заполненное из current_checklist):
- role — см. выше
- schedule_text — для scheduled-ролей (не для dm_assistant / group_moderation)
- timezone — если в расписании есть время
- reminder_message — текст/заголовок сообщения
- search_topic — тема для news_digest или dm_assistant с веб-сводкой
- image_prompt — описание картинки для image_post / dm_assistant
- dm_command — команда без слэша, напр. news (dm_assistant, если interaction_mode command/both)
- scope: dm | group | both — где слушать (dm_assistant): личка, группа или оба
- interaction_mode: command | support | both — command: только по команде; support: на все сообщения; both: и поддержка, и команда
- support_instructions — как отвечать в режиме поддержки (тон, правила, FAQ-логика). Можно взять из reminder_message
- delivery_mode: dm | group — куда отправлять (news_digest, image_post)
- max_chat_id — ID группы
- bot_is_group_admin / bot_can_read_messages
- moderation_stop_words — через запятую (group_moderation)
- moderation_block_links: true/false

Правила диалога:
- Принимай задачу своими словами. НЕ заставляй выбирать из списка и НЕ называй «whitelist».
- Как только пользователь описал задачу — СРАЗУ заполни role и все уже понятные поля в checklist. Не переспрашивай то, что уже сказано.
- НЕ повторяй один и тот же вопрос дважды подряд. Смотри history и current_checklist.
- Если пользователь спрашивает «что умеешь» / «что можешь» — кратко 3–4 примера и попроси описать задачу одной фразой.
- Короткие «ок», «продолжим», «дальше» — объясни ОДИН следующий шаг по missing_fields, не начинай диалог заново.

Примеры (пользователь → role + поля):
- «напоминай каждый день в 9 про встречу» → personal_reminder, schedule_text, reminder_message
- «пиши в группу каждый вечер итог дня» → group_reminder или group_message_log
- «новости про ИИ каждое утро» → news_digest, search_topic, schedule_text
- «отвечай в группе на вопросы, переводи текст с фото» → dm_assistant, scope=group, interaction_mode=support
- «удаляй спам и ссылки в группе» → group_moderation, moderation_stop_words/block_links
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
        return cls(
            role=role,
            schedule_text=_str_or_none(raw.get("schedule_text")),
            timezone=_str_or_none(raw.get("timezone")),
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


def merge_checklist(current: ChecklistState, patch: ChecklistState) -> ChecklistState:
    data = current.to_dict()
    for key, value in patch.to_dict().items():
        if value is not None:
            data[key] = value
    return ChecklistState.from_dict(data)


def apply_checklist_to_agent(agent: AgentInstance, checklist: ChecklistState) -> None:
    cfg = dict(agent.config or {})
    cfg["checklist"] = checklist.to_dict()
    cfg["schedule_text"] = checklist.schedule_text
    cfg["timezone"] = checklist.timezone or cfg.get("timezone") or "Europe/Moscow"
    cfg["reminder_message"] = checklist.reminder_message
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
        if checklist.schedule_text and not checklist.timezone:
            missing.append("timezone")

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
    if user_asks_capabilities(last_user_text):
        lines.append(
            "user_signal: asks_capabilities — кратко 3–4 примера и попроси описать задачу одной фразой"
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

    enriched = ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user))
    local_reply = try_local_onboarding_reply(checklist.to_dict(), last_user)
    use_local = local_reply is not None and (
        user_asks_capabilities(last_user)
        or user_needs_clarification(last_user)
        or user_wants_continue(last_user)
        or (enriched.role and enriched.role != checklist.role)
        or (enriched.role and len(last_user.strip()) >= 15)
    )
    if use_local:
        return LlmTurnResult(reply=local_reply, checklist=enriched)

    checklist = enriched

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
        fallback_checklist = ChecklistState.from_dict(
            apply_message_hints(checklist.to_dict(), last_user),
        )
        return LlmTurnResult(
            reply=build_parse_fallback_reply(fallback_checklist.to_dict(), last_user),
            checklist=fallback_checklist,
        )

    data = _parse_llm_json(raw)
    if not data:
        logger.warning("Agent LLM JSON parse failed: %s", raw[:300])
        fallback_checklist = ChecklistState.from_dict(
            apply_message_hints(checklist.to_dict(), last_user),
        )
        return LlmTurnResult(
            reply=build_parse_fallback_reply(fallback_checklist.to_dict(), last_user),
            checklist=fallback_checklist,
        )

    patch = ChecklistState.from_dict(data.get("checklist") if isinstance(data.get("checklist"), dict) else {})
    merged = merge_checklist(checklist, patch)
    reply = _str_or_none(data.get("reply")) or "Уточните, пожалуйста, детали задачи."
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

    if user_wants_confirm(last_user) and ready:
        activate = True

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
