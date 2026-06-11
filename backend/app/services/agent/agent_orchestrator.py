"""Агент-оркестратор: цикл LLM + инструменты, каждая итерация LLM тарифицируется."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.models.user import User
from app.services.agent.agent_security import (
    MAX_ORCHESTRATOR_ITERATIONS,
    MAX_TOOL_CALLS_PER_TURN,
    user_consented_test_send,
)
from app.services.agent.agent_tools import (
    agent_runtime_diagnostics,
    execute_agent_tool,
    format_tool_results_for_llm,
)
from app.services.agent.context_reset import history_messages_for_agent
from app.services.agent.llm_onboarding import (
    AGENT_SYSTEM_PROMPT,
    ChecklistState,
    LlmTurnResult,
    _context_block,
    _parse_llm_json,
    _sanitize_agent_reply,
    apply_message_hints,
    build_parse_fallback_reply,
    checklist_missing_fields,
    finalize_checklist,
    load_checklist,
    merge_checklist,
)
from app.services.agent.intent_hints import _extract_max_chat_id, user_wants_immediate_run, user_wants_today_run
from app.services.agent.operational import bind_chat_to_current_agent, is_operational_max_query
from app.services.agent.llm_onboarding import user_wants_confirm  # noqa: F401 — re-export path
from app.services.agent.agent_status import (
    STATUS_ANALYZING_RESULTS,
    STATUS_THINKING,
    StatusCallback,
    emit_status,
    noop_status,
    tool_status_label,
)
from app.services.providers.factory import resolve_runtime_providers

logger = logging.getLogger(__name__)

TOOLS_APPENDIX = """
Дополнительно: ты можешь вызывать инструменты для проверки MAX без вопросов пользователю.
Когда нужно проверить группу, канал, ошибку отправки или найти информацию — вызови tool_calls.
После получения tool_results — проанализируй и либо вызови ещё инструменты, либо заверши ответ (done=true).

Инструменты (только из списка):
- max_probe_chat {chat_id, send_test?} — проверка чата/канала, опционально тестовое сообщение (send_test только если пользователь просил)
- max_send_test {chat_id} — тестовое сообщение (только по запросу пользователя)
- max_get_chat {chat_id} — информация о чате
- max_list_bot_chats {} — чаты/каналы, куда добавлен бот
- max_resolve_channel_link {link} — chat_id канала по ссылке max.ru/...
- max_read_activity_logs {} — журнал dispatch за 24ч
- web_search {query} — поиск в интернете
- read_thread_summary {} — последние сообщения треда

Безопасность: нельзя слать в чужие chat_id; только привязанные к агенту.
При ошибке MAX — объясни пользователю простым языком, что не так и как исправить.

Формат ответа (JSON):
{
  "reply": "текст пользователю или null пока думаешь",
  "done": false,
  "tool_calls": [{"tool": "max_probe_chat", "arguments": {"chat_id": -123}}],
  "checklist": { ... },
  "ready_for_confirmation": false,
  "confirmation_summary": null,
  "activate": false
}

Когда done=true — tool_calls должен быть пустым, reply обязателен.
"""


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
    checklist = load_checklist(agent)
    history = history_messages_for_agent(messages, agent)
    last_user = history[-1]["text"] if history and history[-1]["role"] == "user" else ""

    if is_operational_max_query(last_user):
        cid = _extract_max_chat_id(last_user)
        if cid is not None:
            bind_chat_to_current_agent(agent, int(cid))

    checklist = ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user))

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    allow_test = user_consented_test_send(last_user)

    tool_trace: list[dict] = []
    status_cb = on_status or noop_status
    extra_system = TOOLS_APPENDIX
    if diagnostic_mode:
        diag = await agent_runtime_diagnostics(db, agent)
        extra_system += f"\n\ndiagnostic_snapshot: {json.dumps(diag, ensure_ascii=False)}"

    for iteration in range(MAX_ORCHESTRATOR_ITERATIONS):
        if iteration > 0:
            allowed, _used, _limit = await limiter.check_search_limit(
                str(user.id), user.plan, user=user
            )
            if not allowed:
                return LlmTurnResult(
                    reply=(
                        "Достигнут дневной лимит запросов. "
                        "Продолжить настройку можно завтра или с тарифом Pro."
                    ),
                    checklist=checklist,
                )

        payload_messages: list[dict[str, str]] = [
            {"role": "system", "text": AGENT_SYSTEM_PROMPT},
            {"role": "system", "text": extra_system},
            {"role": "system", "text": _context_block(user, agent, checklist, last_user)},
        ]
        if tool_trace:
            payload_messages.append(
                {
                    "role": "system",
                    "text": f"tool_results:\n{format_tool_results_for_llm(tool_trace)}",
                }
            )
        payload_messages.extend(history)

        await emit_status(
            status_cb,
            STATUS_THINKING if iteration == 0 else STATUS_ANALYZING_RESULTS,
        )
        raw = await _llm_complete(llm, payload_messages)
        data = _parse_llm_json(raw)
        if not data and iteration < MAX_ORCHESTRATOR_ITERATIONS - 1:
            payload_messages.append(
                {
                    "role": "system",
                    "text": "Ответ должен быть валидным JSON. Повтори с done=true если готов ответить.",
                }
            )
            raw = await _llm_complete(llm, payload_messages)
            data = _parse_llm_json(raw)

        if not data:
            logger.warning("Agent orchestrator JSON failed iter=%s: %s", iteration, raw[:300])
            fallback = finalize_checklist(
                ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user)),
                history=history,
            )
            return LlmTurnResult(
                reply=build_parse_fallback_reply(fallback.to_dict(), last_user),
                checklist=fallback,
            )

        tool_calls = data.get("tool_calls")
        done = bool(data.get("done", True))
        if isinstance(tool_calls, list) and tool_calls and not done:
            if len(tool_trace) >= MAX_TOOL_CALLS_PER_TURN:
                return LlmTurnResult(
                    reply="Слишком много шагов за один запрос. Уточните задачу или напишите «продолжим».",
                    checklist=checklist,
                )
            for call in tool_calls[:6]:
                if not isinstance(call, dict):
                    continue
                tool_name = str(call.get("tool") or "")
                arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                await emit_status(status_cb, tool_status_label(tool_name))
                result = await execute_agent_tool(
                    db,
                    redis_client,
                    user,
                    agent,
                    tool_name,
                    arguments,
                    thread_id=thread_id,
                    allow_test_send=allow_test,
                    user_message=last_user,
                )
                tool_trace.append(result)
            checklist = _merge_checklist_from_data(data, checklist, last_user, history)
            continue

        return _result_from_data(data, checklist, last_user, history, user)

    return LlmTurnResult(
        reply=(
            "Задача сложная — достигнут лимит шагов за один запрос. "
            "Напишите «продолжим» или уточните один пункт."
        ),
        checklist=checklist,
    )


async def _llm_complete(llm, messages: list[dict[str, str]]) -> str:
    if not hasattr(llm, "complete_text"):
        raise AttributeError("complete_text unavailable")
    return await llm.complete_text(  # type: ignore[attr-defined]
        messages, model="pro", max_tokens=1200, temperature=0.35
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
    merged = merge_checklist(checklist, patch, user_text=last_user)
    merged = ChecklistState.from_dict(apply_message_hints(merged.to_dict(), last_user))
    return finalize_checklist(merged, history=history)


def _result_from_data(
    data: dict[str, Any],
    checklist: ChecklistState,
    last_user: str,
    history: list[dict[str, str]],
    user: User,
) -> LlmTurnResult:
    merged = _merge_checklist_from_data(data, checklist, last_user, history)
    reply = _str_or_none(data.get("reply")) or build_parse_fallback_reply(merged.to_dict(), last_user)
    reply = _sanitize_agent_reply(reply, last_user, merged)
    ready = bool(data.get("ready_for_confirmation"))
    summary = _str_or_none(data.get("confirmation_summary"))
    activate = bool(data.get("activate"))

    if not user.max_user_id:
        activate = False

    missing = checklist_missing_fields(merged)
    if user_wants_confirm(last_user) and not missing:
        activate = True
        ready = True
    elif (user_wants_today_run(last_user) or user_wants_immediate_run(last_user)) and not missing:
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


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def user_wants_diagnostic(text: str) -> bool:
    from app.services.agent.operational import is_operational_max_query

    if is_operational_max_query(text):
        return True
    low = (text or "").lower()
    markers = (
        "почему не",
        "не отправ",
        "не работ",
        "не пишет",
        "не постит",
        "ошибк",
        "журнал",
        "диагност",
        "проверь",
        "что не так",
        "статус агента",
        "не приход",
        "сломал",
        "перестал",
    )
    return any(m in low for m in markers)
