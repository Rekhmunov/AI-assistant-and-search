"""Агент-оркестратор: хелперы checklist и тонкая обёртка над unified loop."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance
from app.models.message import Message
from app.models.user import User
from app.services.agent.agent_status import StatusCallback
from app.services.agent.llm_onboarding import (
    ChecklistState,
    LlmTurnResult,
    _sanitize_agent_reply,
    apply_message_hints,
    build_parse_fallback_reply,
    checklist_missing_fields,
    finalize_checklist,
    merge_checklist,
)
from app.services.agent.intent_hints import user_wants_immediate_run, user_wants_today_run

logger = logging.getLogger(__name__)


async def run_agent_turn(
    db,
    redis_client,
    user: User,
    agent: AgentInstance,
    messages: list[Message],
    limiter: RateLimiter,
    *,
    thread_id: UUID,
    diagnostic_mode: bool = False,
    on_status: StatusCallback | None = None,
) -> LlmTurnResult:
    """Обратная совместимость: делегирует в единый onboarding loop."""
    from app.services.agent.agent_loop import run_onboarding_loop

    return await run_onboarding_loop(
        db,
        redis_client,
        user,
        agent,
        messages,
        limiter,
        thread_id=thread_id,
        diagnostic_mode=diagnostic_mode,
        on_status=on_status,
    )


def _merge_checklist_from_data(
    data: dict[str, Any],
    checklist: ChecklistState,
    last_user: str,
    history: list[dict[str, str]],
) -> ChecklistState:
    patch = ChecklistState.from_dict(
        data.get("checklist") if isinstance(data.get("checklist"), dict) else {}
    )
    # Доверяем LLM-патчу — не дополняем keyword-инференсом после LLM.
    merged = merge_checklist(checklist, patch, user_text=last_user)
    return finalize_checklist(merged, history=history)


def _result_from_data(
    data: dict[str, Any],
    checklist: ChecklistState,
    last_user: str,
    history: list[dict[str, str]],
    user: User,
    *,
    is_assistant_template: bool = False,
) -> LlmTurnResult:
    merged = _merge_checklist_from_data(data, checklist, last_user, history)
    reply = _str_or_none(data.get("reply")) or build_parse_fallback_reply(merged.to_dict(), last_user)
    reply = _sanitize_agent_reply(reply, last_user, merged)
    ready = bool(data.get("ready_for_confirmation"))
    summary = _str_or_none(data.get("confirmation_summary"))
    activate = bool(data.get("activate"))

    # Личный ассистент активируется без MAX и без checklist-полей
    if is_assistant_template:
        return LlmTurnResult(
            reply=reply,
            checklist=merged,
            ready_for_confirmation=ready,
            confirmation_summary=summary,
            activate=activate,
        )

    if not user.max_user_id:
        activate = False

    missing = checklist_missing_fields(merged)

    # Не форсируем activate по ключевым словам — LLM решает.
    # Структурный барьер: нельзя активировать с незаполненными полями.
    if activate and missing:
        activate = False

    return LlmTurnResult(
        reply=reply,
        checklist=merged,
        ready_for_confirmation=ready,
        confirmation_summary=summary,
        activate=activate and bool(user.max_user_id),
    )


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def user_wants_diagnostic(text: str) -> bool:
    """
    Определяет диагностический запрос — когда пользователь спрашивает о проблеме
    с работой агента, а не задаёт новую задачу настройки.
    Используется только как хинт для выбора diagnostic_mode в tool loop.
    """
    from app.services.agent.operational import is_operational_max_query

    # Явные проверки доступа/прав — всегда диагностика
    if is_operational_max_query(text):
        return True
    # Для остального — LLM рассуждает через diagnostic_snapshot в контексте
    # если agent_status=ACTIVE и пользователь описывает проблему
    return False
