"""Единый цикл агента: tools + рефлексия + память."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance
from app.models.message import Message
from app.models.user import User
from app.services.agent.agent_reflection import critique_agent_reply, should_reflect
from app.services.agent.agent_security import (
    MAX_ORCHESTRATOR_ITERATIONS,
    MAX_TOOL_CALLS_PER_TURN,
    user_consented_test_send,
)
from app.services.agent.agent_spec import load_agent_spec, spec_context_block, sync_spec_from_checklist
from app.services.agent.agent_status import (
    STATUS_ANALYZING_RESULTS,
    STATUS_MEMORY_UPDATE,
    STATUS_REFLECTING,
    STATUS_THINKING,
    StatusCallback,
    emit_status,
    noop_status,
    tool_status_label,
)
from app.services.agent.agent_tools import execute_agent_tool, format_tool_results_for_llm
from app.services.agent.context_reset import history_messages_for_agent
from app.services.agent.agent_orchestrator import _merge_checklist_from_data, _result_from_data
from app.services.agent.llm_onboarding import (
    AGENT_SYSTEM_PROMPT,
    ChecklistState,
    LlmTurnResult,
    _context_block,
    _parse_llm_json,
    apply_message_hints,
    build_parse_fallback_reply,
    finalize_checklist,
    load_checklist,
)
from app.services.agent.max_capabilities import tools_appendix_for_mode
from app.services.agent.search_reply import prefer_web_search_answer
from app.services.agent.source_display import prepare_agent_reply_for_ui
from app.services.agent.agent_tool_feedback import (
    PROMISE_WITHOUT_TOOLS_NUDGE,
    ensure_action_feedback,
    reply_is_deferred_promise,
    user_expects_immediate_max_action,
)
from app.services.agent.thread_memory import update_thread_memory_after_turn
from app.services.providers.factory import resolve_runtime_providers

logger = logging.getLogger(__name__)

RUNTIME_SYSTEM_PROMPT = """Ты — автономный агент Glosix в мессенджере MAX.
Используй agent_spec, thread_memory и tools. Действуй самостоятельно: сам выбирай формат поста, длину, иллюстрации.
Для актуальных данных — web_search. Для учёта: store_agent_record. Для отчётов: query_agent_records + max_send_file.
Если категория неясна — спроси в чат. Отвечай кратко на русском."""


@dataclass
class RuntimeLoopResult:
    text: str
    attachments: list[dict] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)


async def run_onboarding_loop(
    db: AsyncSession,
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
    """Настройка в Glosix: checklist + рефлексия + память."""
    checklist = load_checklist(agent)
    history = history_messages_for_agent(messages, agent)
    last_user = history[-1]["text"] if history and history[-1]["role"] == "user" else ""
    from app.services.agent.intent_hints import _extract_max_chat_id
    from app.services.agent.operational import bind_chat_to_current_agent

    cid = _extract_max_chat_id(last_user)
    if cid is not None:
        bind_chat_to_current_agent(agent, int(cid))

    checklist = ChecklistState.from_dict(apply_message_hints(checklist.to_dict(), last_user))
    sync_spec_from_checklist(agent, checklist.to_dict(), last_user)

    result, tool_trace = await _tool_loop(
        db,
        redis_client,
        user,
        agent,
        limiter,
        thread_id=thread_id,
        user_text=last_user,
        history=history,
        mode="onboarding",
        checklist=checklist,
        diagnostic_mode=diagnostic_mode,
        on_status=on_status,
    )
    if isinstance(result, LlmTurnResult):
        draft = prefer_web_search_answer(result.reply, tool_trace)
        draft, sources = prepare_agent_reply_for_ui(draft, tool_trace)
        if draft != result.reply or sources:
            result = LlmTurnResult(
                reply=draft,
                checklist=result.checklist,
                ready_for_confirmation=result.ready_for_confirmation,
                confirmation_summary=result.confirmation_summary,
                activate=result.activate,
                sources=sources,
            )
        spec = load_agent_spec(agent)
        llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
        if should_reflect(user_text=last_user, draft_reply=draft, runtime=False):
            await emit_status(on_status, STATUS_REFLECTING)
            reflection = await critique_agent_reply(
                llm,
                user_text=last_user,
                draft_reply=draft,
                spec_context=spec_context_block(spec) + "\n" + _context_block(user, agent, result.checklist, last_user),
                answer_model=answer_model,
            )
            if reflection.revised_reply and (not reflection.ok or reflection.revised_reply != draft):
                revised, revised_sources = prepare_agent_reply_for_ui(
                    reflection.revised_reply,
                    tool_trace,
                )
                result = LlmTurnResult(
                    reply=revised,
                    checklist=result.checklist,
                    ready_for_confirmation=result.ready_for_confirmation,
                    confirmation_summary=result.confirmation_summary,
                    activate=result.activate,
                    sources=revised_sources or result.sources,
                )
        await emit_status(on_status, STATUS_MEMORY_UPDATE)
        await update_thread_memory_after_turn(
            db,
            redis_client,
            user,
            agent,
            thread_id=thread_id,
            user_text=last_user,
            assistant_text=result.reply,
            tool_summary=_tool_summary(tool_trace),
        )
        sync_spec_from_checklist(agent, result.checklist.to_dict(), last_user)
        return result
    return result


async def run_runtime_loop(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    limiter: RateLimiter,
    *,
    thread_id: UUID,
    user_text: str,
    chat_id: int | None = None,
    author: str = "",
    on_status: StatusCallback | None = None,
) -> RuntimeLoopResult:
    """Исполнение в MAX: tools + рефлексия без checklist."""
    spec = load_agent_spec(agent)
    allow_test = True  # активный агент в MAX — пользователь инициировал диалог

    result, tool_trace = await _tool_loop(
        db,
        redis_client,
        user,
        agent,
        limiter,
        thread_id=thread_id,
        user_text=user_text,
        history=[{"role": "user", "text": user_text}],
        mode="runtime",
        checklist=None,
        diagnostic_mode=False,
        on_status=on_status,
        allow_test_send=allow_test,
        runtime_chat_id=chat_id,
        author=author,
    )
    if isinstance(result, RuntimeLoopResult):
        text = prefer_web_search_answer(result.text, result.tool_trace or tool_trace)
        if text != result.text:
            result = RuntimeLoopResult(
                text=text,
                attachments=result.attachments,
                tool_trace=result.tool_trace,
            )
        llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
        if should_reflect(user_text=user_text, draft_reply=result.text, runtime=True):
            await emit_status(on_status, STATUS_REFLECTING)
            reflection = await critique_agent_reply(
                llm,
                user_text=user_text,
                draft_reply=result.text,
                spec_context=spec_context_block(spec),
                answer_model=answer_model,
            )
            if reflection.revised_reply and (not reflection.ok or reflection.notes):
                result = RuntimeLoopResult(
                    text=reflection.revised_reply,
                    attachments=result.attachments,
                    tool_trace=result.tool_trace,
                )
        if thread_id:
            await emit_status(on_status, STATUS_MEMORY_UPDATE)
            await update_thread_memory_after_turn(
                db,
                redis_client,
                user,
                agent,
                thread_id=thread_id,
                user_text=user_text,
                assistant_text=result.text,
                tool_summary=_tool_summary(tool_trace),
            )
        return result
    return RuntimeLoopResult(text="Не удалось обработать запрос.", attachments=[])


async def _tool_loop(
    db,
    redis_client,
    user: User,
    agent: AgentInstance,
    limiter: RateLimiter,
    *,
    thread_id: UUID,
    user_text: str,
    history: list[dict[str, str]],
    mode: Literal["onboarding", "runtime"],
    checklist: ChecklistState | None,
    diagnostic_mode: bool,
    on_status: StatusCallback | None,
    allow_test_send: bool | None = None,
    runtime_chat_id: int | None = None,
    author: str = "",
) -> tuple[LlmTurnResult | RuntimeLoopResult, list[dict]]:
    from app.services.agent.agent_tools import agent_runtime_diagnostics

    llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    allow_test = allow_test_send if allow_test_send is not None else user_consented_test_send(user_text)
    tool_trace: list[dict] = []
    status_cb = on_status or noop_status
    spec = load_agent_spec(agent)

    extra = tools_appendix_for_mode(runtime=mode == "runtime")
    if diagnostic_mode and mode == "onboarding":
        diag = await agent_runtime_diagnostics(db, agent)
        extra += f"\n\ndiagnostic_snapshot: {json.dumps(diag, ensure_ascii=False)}"

    attachments: list[dict] = []
    outbound_sent = False
    loop_nudges: list[str] = []

    for iteration in range(MAX_ORCHESTRATOR_ITERATIONS):
        if iteration > 0:
            allowed, _used, _limit = await limiter.check_search_limit(str(user.id), user.plan, user=user)
            if not allowed:
                msg = "Достигнут дневной лимит запросов. Попробуйте завтра или с тарифом Pro."
                if mode == "runtime":
                    return RuntimeLoopResult(text=msg, attachments=[]), tool_trace
                return (
                    LlmTurnResult(reply=msg, checklist=checklist or ChecklistState()),
                    tool_trace,
                )

        payload: list[dict[str, str]] = []
        if mode == "runtime":
            payload.append({"role": "system", "text": RUNTIME_SYSTEM_PROMPT})
        else:
            payload.append({"role": "system", "text": AGENT_SYSTEM_PROMPT})
        payload.append({"role": "system", "text": extra})
        payload.append({"role": "system", "text": spec_context_block(spec)})
        if mode == "onboarding" and checklist is not None:
            payload.append({"role": "system", "text": _context_block(user, agent, checklist, user_text)})
        if runtime_chat_id is not None:
            payload.append({"role": "system", "text": f"current_max_chat_id: {runtime_chat_id}"})
        for nudge in loop_nudges:
            payload.append({"role": "system", "text": nudge})
        if tool_trace:
            payload.append(
                {"role": "system", "text": f"tool_results:\n{format_tool_results_for_llm(tool_trace)}"}
            )
        payload.extend(history if mode == "onboarding" else history[-6:])

        await emit_status(status_cb, STATUS_THINKING if iteration == 0 else STATUS_ANALYZING_RESULTS)
        raw = await _llm_complete(llm, payload)
        data = _parse_llm_json(raw)
        if not data and iteration < MAX_ORCHESTRATOR_ITERATIONS - 1:
            payload.append(
                {
                    "role": "system",
                    "text": "Ответ должен быть валидным JSON. Повтори с done=true если готов ответить.",
                }
            )
            raw = await _llm_complete(llm, payload)
            data = _parse_llm_json(raw)

        if not data:
            logger.warning("Unified loop JSON failed iter=%s: %s", iteration, raw[:300])
            if mode == "runtime":
                return RuntimeLoopResult(text="Сейчас не удалось обработать запрос.", attachments=[]), tool_trace
            fb = finalize_checklist(
                ChecklistState.from_dict(apply_message_hints((checklist or ChecklistState()).to_dict(), user_text)),
                history=history,
            )
            return LlmTurnResult(reply=build_parse_fallback_reply(fb.to_dict(), user_text), checklist=fb), tool_trace

        tool_calls = data.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            if len(tool_trace) >= MAX_TOOL_CALLS_PER_TURN:
                msg = "Слишком много шагов за один запрос. Уточните задачу."
                if mode == "runtime":
                    return RuntimeLoopResult(text=msg, attachments=attachments), tool_trace
                return (
                    LlmTurnResult(reply=msg, checklist=checklist or ChecklistState()),
                    tool_trace,
                )
            for call in tool_calls[:6]:
                if not isinstance(call, dict):
                    continue
                tool_name = str(call.get("tool") or "")
                args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                await emit_status(status_cb, tool_status_label(tool_name))
                result = await execute_agent_tool(
                    db,
                    redis_client,
                    user,
                    agent,
                    tool_name,
                    args,
                    thread_id=thread_id,
                    allow_test_send=allow_test,
                    user_message=user_text,
                    runtime_chat_id=runtime_chat_id,
                    author=author,
                    on_status=status_cb,
                )
                tool_trace.append(result)
                if tool_name in {"max_send_file", "max_send_message"} and result.get("ok"):
                    outbound_sent = True
                    attachments = []
                elif tool_name == "max_send_file" and result.get("ok") and isinstance(result.get("result"), dict):
                    att = result["result"].get("attachments")
                    if isinstance(att, list):
                        attachments = att
            if mode == "onboarding" and checklist is not None:
                checklist = _merge_checklist_from_data(data, checklist, user_text, history)
            continue

        reply = str(data.get("reply") or "").strip()
        if (
            not tool_trace
            and reply_is_deferred_promise(reply)
            and user_expects_immediate_max_action(user_text)
            and not loop_nudges
            and iteration < MAX_ORCHESTRATOR_ITERATIONS - 1
        ):
            loop_nudges.append(PROMISE_WITHOUT_TOOLS_NUDGE)
            continue

        if mode == "runtime":
            return RuntimeLoopResult(
                text=ensure_action_feedback(reply, tool_trace, user_text),
                attachments=attachments,
                tool_trace=tool_trace,
            ), tool_trace

        assert checklist is not None
        result = _result_from_data(data, checklist, user_text, history, user)
        final_reply = ensure_action_feedback(result.reply, tool_trace, user_text)
        if final_reply != result.reply:
            result = LlmTurnResult(
                reply=final_reply,
                checklist=result.checklist,
                ready_for_confirmation=result.ready_for_confirmation,
                confirmation_summary=result.confirmation_summary,
                activate=result.activate,
                sources=result.sources,
            )
        return result, tool_trace

    msg = ensure_action_feedback(
        "Задача сложная — достигнут лимит шагов. Напишите «продолжим» или уточните.",
        tool_trace,
        user_text,
    )
    if mode == "runtime":
        return RuntimeLoopResult(text=msg, attachments=attachments, tool_trace=tool_trace), tool_trace
    return LlmTurnResult(reply=msg, checklist=checklist or ChecklistState()), tool_trace


async def _llm_complete(llm, messages: list[dict[str, str]]) -> str:
    return await llm.complete_text(
        messages, model="pro", max_tokens=1400, temperature=0.35
    )


def _tool_summary(tool_trace: list[dict]) -> str:
    parts = []
    for item in tool_trace[-6:]:
        name = item.get("tool") or "?"
        ok = item.get("ok", False)
        parts.append(f"{name}:{'ok' if ok else 'err'}")
    return ", ".join(parts)
