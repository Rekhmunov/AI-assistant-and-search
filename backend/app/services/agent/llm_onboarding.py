"""LLM-диалог настройки агента с JSON-чеклистом."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.message import Message, MessageRole
from app.models.user import User
from app.services.agent.capabilities import (
    CAPABILITIES_REPLY,
    apply_message_hints,
    build_parse_fallback_reply,
    user_asks_capabilities,
    user_needs_clarification,
)
from app.services.agent.constants import CANCEL_PHRASES, SUPPORTED_ROLE_LABELS
from app.services.agent.onboarding import validate_activation
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

VALID_ROLES = frozenset(
    {
        AgentRole.PERSONAL_REMINDER.value,
        AgentRole.GROUP_REMINDER.value,
        AgentRole.GROUP_MESSAGE_LOG.value,
    }
)

AGENT_SYSTEM_PROMPT = """Ты — ассистент настройки агента Glosix для мессенджера MAX.
Веди живой диалог на русском. Отвечай только валидным JSON (без markdown-обёртки).

Что технически доступно (внутренняя модель — НЕ озвучивай списком без запроса):
• Писать пользователю в личный чат MAX (dm_out).
• Писать в группу MAX, где бот Glosix — администратор (group_out).
• Читать сообщения группы и присылать сводку/отчёт в личный чат (group_in + dm_out).
• Срабатывание по расписанию или разово («завтра в 9:00», «через 15 минут», «каждый понедельник»).

Внутренние role (определи сам по смыслу запроса пользователя):
- personal_reminder — уведомления/напоминания в личный чат пользователя.
- group_reminder — сообщения/напоминания в группу MAX.
- group_message_log — чтение группы + сводка в личный чат.

Чеклист (заполняй по мере диалога, null если неизвестно; уже заполненное из current_checklist сохраняй):
- role: personal_reminder | group_reminder | group_message_log | null
- schedule_text: когда срабатывать (естественный язык)
- timezone: IANA (Europe/Moscow) или UTC+N — уточни, если в расписании есть время суток
- reminder_message: текст сообщения или сводки
- max_chat_id: числовой ID группы (для group_*)
- bot_is_group_admin: true/false/null
- bot_can_read_messages: true/false/null (обязательно true для group_message_log)

Правила диалога:
- Принимай задачу своими словами. НЕ заставляй выбирать из списка и НЕ называй «whitelist».
- Если пользователь спрашивает «что умеешь» / «что можешь» — кратко 3–4 примера возможностей.
- Если просят невозможное (бот не админ в группе, чтение без прав, сторонние сервисы, диалог-бот в MAX) —
  скажи, что сейчас это не поддерживается, без перечисления всего whitelist.
- Если пользователь не понял («не понял», «не совсем понял», «поясни», «что дальше») —
  НЕ сбрасывай диалог; переформулируй последний шаг проще, опираясь на current_checklist.
  Объясняй один следующий шаг, не сваливай все вопросы разом.
- Задавай по одному недостающему параметру за раз (кроме случая, когда пользователь сам дал всё сразу).
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
    "max_chat_id": null,
    "bot_is_group_admin": null,
    "bot_can_read_messages": null
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
    max_chat_id: int | None = None
    bot_is_group_admin: bool | None = None
    bot_can_read_messages: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "schedule_text": self.schedule_text,
            "timezone": self.timezone,
            "reminder_message": self.reminder_message,
            "max_chat_id": self.max_chat_id,
            "bot_is_group_admin": self.bot_is_group_admin,
            "bot_can_read_messages": self.bot_can_read_messages,
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
        return cls(
            role=role,
            schedule_text=_str_or_none(raw.get("schedule_text")),
            timezone=_str_or_none(raw.get("timezone")),
            reminder_message=_str_or_none(raw.get("reminder_message")),
            max_chat_id=chat_id,
            bot_is_group_admin=_bool_or_none(raw.get("bot_is_group_admin")),
            bot_can_read_messages=_bool_or_none(raw.get("bot_can_read_messages")),
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
            "reminder_message": cfg.get("reminder_message"),
            "max_chat_id": agent.max_chat_id or cfg.get("max_chat_id"),
            "bot_is_group_admin": cfg.get("bot_is_group_admin"),
            "bot_can_read_messages": cfg.get("bot_can_read_messages"),
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
    cfg["bot_is_group_admin"] = checklist.bot_is_group_admin
    cfg["bot_can_read_messages"] = checklist.bot_can_read_messages
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
    if not checklist.role:
        missing.append("role")
    if not checklist.schedule_text:
        missing.append("schedule")
    if checklist.schedule_text and not checklist.timezone:
        missing.append("timezone")
    if not checklist.reminder_message:
        missing.append("message")
    if checklist.role in {AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MESSAGE_LOG.value}:
        if not checklist.max_chat_id:
            missing.append("group_chat")
        if checklist.bot_is_group_admin is not True:
            missing.append("bot_admin")
        if checklist.role == AgentRole.GROUP_MESSAGE_LOG.value and checklist.bot_can_read_messages is not True:
            missing.append("bot_read")
    return missing


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
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
            "user_signal: asks_capabilities — кратко перечисли 3–4 примера того, что умеет агент"
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

    if user_asks_capabilities(last_user):
        hinted = ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user))
        return LlmTurnResult(reply=CAPABILITIES_REPLY, checklist=hinted)

    checklist = ChecklistState.from_dict(
        apply_message_hints(checklist.to_dict(), last_user),
    )

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
        return LlmTurnResult(
            reply=build_parse_fallback_reply(checklist.to_dict(), last_user),
            checklist=checklist,
        )

    data = _parse_llm_json(raw)
    if not data:
        logger.warning("Agent LLM JSON parse failed: %s", raw[:300])
        return LlmTurnResult(
            reply=build_parse_fallback_reply(checklist.to_dict(), last_user),
            checklist=checklist,
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
    return (
        "Проверьте настройки перед запуском:\n"
        f"• Задача: {role_label}\n"
        f"• Расписание: {checklist.schedule_text or '—'}\n"
        f"• Часовой пояс: {checklist.timezone or 'Europe/Moscow'}\n"
        f"• Текст: {checklist.reminder_message or '—'}\n"
        + (f"• Группа MAX: {checklist.max_chat_id}\n" if checklist.max_chat_id else "")
        + "\nЗапустить агента? Ответьте «да» или «подтверждаю»."
    )


def try_validate_checklist(checklist: ChecklistState) -> None:
    class _AgentShim:
        role = checklist.role
        max_chat_id = checklist.max_chat_id
        config = {
            "schedule_text": checklist.schedule_text,
            "reminder_message": checklist.reminder_message,
        }

    validate_activation(_AgentShim())  # type: ignore[arg-type]
