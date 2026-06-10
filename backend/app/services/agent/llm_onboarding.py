"""LLM-диалог настройки агента с JSON-чеклистом."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.message import Message, MessageRole
from app.models.user import User
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
Веди живой диалог на русском. Отвечай только валидным JSON (без markdown).

Доступные сценарии (whitelist):
1) personal_reminder — личное напоминание пользователю в чат Glosix в MAX.
2) group_reminder — напоминание в групповом чате MAX (бот должен быть администратором).
3) group_message_log — бот читает сообщения группы и присылает сводки в личный чат пользователя.

Чеклист (заполняй по мере диалога, null если неизвестно):
- role: personal_reminder | group_reminder | group_message_log | null
- schedule_text: когда срабатывать (естественный язык, MSK): «завтра в 9:00», «каждый понедельник в 10:00», «через 15 минут», «сегодня в 18:30»
- reminder_message: текст напоминания или сводки
- max_chat_id: числовой ID группового чата (только для group_*)
- bot_is_group_admin: true/false/null — бот Glosix назначен админом группы
- bot_can_read_messages: true/false/null — у бота есть право читать сообщения (для group_message_log)

Правила:
- Если max_linked=false, объясни привязку MAX: Профиль → войти через MAX / привязать аккаунт. Не активируй агента.
- Для group_* задавай наводящие вопросы, пока чеклист не полон.
- Если пользователь сразу дал всё — заполни чеклист и переходи к подтверждению.
- Когда все обязательные поля заполнены, ready_for_confirmation=true и напиши итог в confirmation_summary.
- activate=true только если пользователь явно подтвердил итог (да/подтверждаю) И max_linked=true.
- Если запрос вне whitelist — вежливо откажи и предложи один из трёх сценариев.
- reply — текст пользователю (можно markdown), без дублирования всего JSON.

Формат ответа:
{
  "reply": "текст",
  "checklist": {
    "role": null,
    "schedule_text": null,
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
    reminder_message: str | None = None
    max_chat_id: int | None = None
    bot_is_group_admin: bool | None = None
    bot_can_read_messages: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "schedule_text": self.schedule_text,
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
            out.append({"role": "user", "content": m.content})
        elif m.role == MessageRole.ASSISTANT:
            out.append({"role": "assistant", "content": m.content})
    return out[-20:]


def _context_block(user: User, agent: AgentInstance, checklist: ChecklistState) -> str:
    cfg = dict(agent.config or {})
    registered = cfg.get("registered_group_chat_id")
    lines = [
        f"max_linked: {bool(user.max_user_id)}",
        f"max_user_id: {user.max_user_id or 'нет'}",
        f"agent_status: {agent.status}",
        f"registered_group_chat_id: {registered or 'нет'}",
        f"current_checklist: {json.dumps(checklist.to_dict(), ensure_ascii=False)}",
        "supported_roles: " + ", ".join(SUPPORTED_ROLE_LABELS.keys()),
    ]
    return "\n".join(lines)


async def run_llm_turn(
    db,
    redis_client,
    user: User,
    agent: AgentInstance,
    messages: list[Message],
    user_text: str,
) -> LlmTurnResult:
    checklist = load_checklist(agent)
    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)

    payload_messages: list[dict[str, str]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "system", "content": _context_block(user, agent, checklist)},
        *_history_messages(messages),
        {"role": "user", "content": user_text},
    ]

    raw = ""
    if hasattr(llm, "complete_text"):
        raw = await llm.complete_text(payload_messages, model="pro", max_tokens=900, temperature=0.3)  # type: ignore[attr-defined]
    else:
        raw = json.dumps(
            {
                "reply": "Расскажите, какую задачу вы хотите поручить агенту в MAX?",
                "checklist": checklist.to_dict(),
                "ready_for_confirmation": False,
                "activate": False,
            },
            ensure_ascii=False,
        )

    data = _parse_llm_json(raw)
    if not data:
        logger.warning("Agent LLM JSON parse failed: %s", raw[:300])
        return LlmTurnResult(
            reply="Не совсем понял. Опишите задачу агента своими словами — напоминание в личный чат или работу с группой в MAX.",
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

    if user_wants_confirm(user_text) and ready:
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
