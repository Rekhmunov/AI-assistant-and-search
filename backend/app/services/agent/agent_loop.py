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
    AgentStatusReporter,
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
from app.services.agent.agent_tool_feedback import ensure_action_feedback
from app.services.agent.thread_memory import update_thread_memory_after_turn
from app.services.providers.factory import resolve_runtime_providers

logger = logging.getLogger(__name__)

RUNTIME_SYSTEM_PROMPT = """Ты — умный агент Glosix в мессенджере MAX.
Используй agent_spec, thread_memory и tools. Действуй самостоятельно.

АЛГОРИТМ перед каждым ответом:
1. ПЛАН — прочитай историю диалога, пойми что нужно пользователю,
   определи что уже знаешь и что нужно выяснить или сделать.
2. ДЕЙСТВИЕ — вызови нужные tools, не описывай планы словами.
3. ПРОВЕРКА — все части задачи выполнены? Ответ использует данные из tools?

Инструменты:
• Текст в чат: max_send_message(chat_id=..., text="...")
• Картинка: max_send_file(chat_id=..., instruction="...", format="image")
• Документ/Excel: max_send_file(chat_id=..., instruction="...", format="docx"/"pdf"/"xlsx")
• Интернет: web_search
• Учёт: store_agent_record / query_agent_records
• Записи секретаря: query_secretary_records(table, category=null, limit=100) — читает данные из группового секретаря пользователя
• Возможности MAX: read_max_api_docs
• База знаний: read_knowledge_base
• Сохранить инструкцию: save_agent_instructions(text) — сохраняет текст как инструкцию агента

Память:
• После важных открытий — update_agent_memory (chat_id, предпочтения, права бота).

Ошибки:
• tool ok=false → error_human → объясни причину и что делать, без технических кодов.

Фото пользователя → vision_context передаётся автоматически.
Краткие ответы на русском. Один вопрос за раз если чего-то не хватает."""


@dataclass
class RuntimeLoopResult:
    text: str
    attachments: list[dict] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)
    outbound_sent: bool = False  # True = сообщение уже отправлено инструментом


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
    reporter: AgentStatusReporter | None = None,
    file_hint: str = "",
) -> LlmTurnResult:
    """Настройка в Glosix: классификатор → специализированный промпт → рефлексия → память."""
    from app.services.agent.classifier import classify_user_intent, get_system_prompt
    from app.services.agent.intent_hints import _extract_max_chat_id
    from app.services.agent.operational import bind_chat_to_current_agent

    checklist = load_checklist(agent)
    history = history_messages_for_agent(messages, agent)
    last_user = history[-1]["text"] if history and history[-1]["role"] == "user" else ""

    cid = _extract_max_chat_id(last_user)
    if cid is not None:
        bind_chat_to_current_agent(agent, int(cid))

    sync_spec_from_checklist(agent, checklist.to_dict(), last_user)

    # Шаг 1 — выбор промпта
    # Приоритет: template из конфига агента → классификатор → общий промпт
    from app.services.agent.templates import get_template_prompt

    agent_cfg = dict(agent.config or {})
    template = agent_cfg.get("template")
    template_prompt = get_template_prompt(template)

    specialized_prompt: str | None = None
    classification_plan: str | None = None

    if template_prompt:
        # Шаблонный агент — используем специализированный промпт без классификатора
        specialized_prompt = template_prompt
        logger.info("Agent using template=%s prompt", template)
    elif last_user and not diagnostic_mode:
        # Нет шаблона — классифицируем задачу
        await emit_status(on_status, "Определяю задачу…")
        llm_for_classify, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
        clf = await classify_user_intent(llm_for_classify, last_user, history[:-1])
        category = clf.category
        classification_plan = clf.plan
        logger.info("Agent classified: category=%s plan=%s ready=%s", category, clf.plan[:80], clf.ready)

        if not clf.ready and clf.confirm:
            return LlmTurnResult(
                reply=clf.confirm,
                checklist=checklist,
                ready_for_confirmation=False,
                activate=False,
            )

        if reporter and classification_plan:
            await reporter.emit_thinking(f"[{category}] {classification_plan}")

        specialized_prompt = get_system_prompt(category)

    # Оптимизация #3: для шаблонных агентов с коротким диалогом провайдер
    # уже разрешён в _tool_loop — переиспользуем результат вместо второго вызова.
    # resolve_runtime_providers лениво кешируется внутри сессии.
    is_template = bool(specialized_prompt)

    effective_user_text = last_user + file_hint if file_hint else last_user
    result, tool_trace = await _tool_loop(
        db,
        redis_client,
        user,
        agent,
        limiter,
        thread_id=thread_id,
        user_text=effective_user_text,
        history=history,
        mode="onboarding",
        checklist=checklist,
        diagnostic_mode=diagnostic_mode,
        on_status=on_status,
        reporter_obj=reporter,
        override_system_prompt=specialized_prompt,
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
        if should_reflect(user_text=last_user, draft_reply=draft, runtime=False, tool_trace=tool_trace):
            await emit_status(on_status, STATUS_REFLECTING)
            reflection = await critique_agent_reply(
                llm,
                user_text=last_user,
                draft_reply=draft,
                spec_context=spec_context_block(spec) + "\n" + _context_block(user, agent, result.checklist, last_user),
                answer_model=answer_model,
            )
            if (
                reflection.revised_reply
                and (not reflection.ok or reflection.revised_reply != draft)
            ):
                revised, revised_sources = prepare_agent_reply_for_ui(
                    reflection.revised_reply,
                    tool_trace,
                )
                if not revised.strip():
                    revised = draft
                result = LlmTurnResult(
                    reply=revised,
                    checklist=result.checklist,
                    ready_for_confirmation=result.ready_for_confirmation,
                    confirmation_summary=result.confirmation_summary,
                    activate=result.activate,
                    sources=revised_sources or result.sources,
                )

        # Оптимизация #1: для шаблонных агентов с коротким диалогом (≤8 сообщений)
        # не суммаризируем память — история и так помещается в контекст.
        # Memory update — отдельный LLM-вызов, при 3-5 ходах напоминания он лишний.
        skip_memory_update = is_template and len(history) <= 8
        if not skip_memory_update:
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
    override_runtime_prompt: str | None = None,
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
        override_system_prompt=override_runtime_prompt,
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
        if result.outbound_sent:
            return result
        if should_reflect(user_text=user_text, draft_reply=result.text, runtime=True, tool_trace=result.tool_trace):
            await emit_status(on_status, STATUS_REFLECTING)
            reflection = await critique_agent_reply(
                llm,
                user_text=user_text,
                draft_reply=result.text,
                spec_context=spec_context_block(spec),
                answer_model=answer_model,
            )
            if reflection.revised_reply and (not reflection.ok or reflection.notes):
                revised_text = reflection.revised_reply.strip() or result.text
                result = RuntimeLoopResult(
                    text=revised_text,
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
    reporter_obj: AgentStatusReporter | None = None,
    override_system_prompt: str | None = None,
) -> tuple[LlmTurnResult | RuntimeLoopResult, list[dict]]:
    from app.services.agent.agent_tools import agent_runtime_diagnostics

    llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)

    if allow_test_send is not None:
        allow_test = allow_test_send
    elif mode == "runtime":
        # В MAX-runtime пользователь сам инициировал диалог — разрешаем всегда
        allow_test = True
    else:
        cfg = dict(agent.config or {})
        allow_test = user_consented_test_send(
            user_text,
            agent_status=agent.status,
            awaiting_confirmation=bool(cfg.get("awaiting_confirmation")),
        )

    tool_trace: list[dict] = []
    status_cb = on_status or noop_status
    spec = load_agent_spec(agent)

    # Для шаблонных агентов не добавляем общий каталог инструментов —
    # шаблонный промпт сам описывает только нужные инструменты.
    is_template_agent = bool(override_system_prompt)
    if is_template_agent:
        extra = _template_tools_appendix(runtime=mode == "runtime")
    else:
        extra = tools_appendix_for_mode(runtime=mode == "runtime")
    if diagnostic_mode and mode == "onboarding":
        diag = await agent_runtime_diagnostics(db, agent)
        extra += f"\n\ndiagnostic_snapshot: {json.dumps(diag, ensure_ascii=False)}"

    attachments: list[dict] = []
    outbound_sent = False

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
        if override_system_prompt:
            # Шаблонный промпт имеет приоритет — и в онбординге, и в runtime
            payload.append({"role": "system", "text": override_system_prompt})
        elif mode == "runtime":
            payload.append({"role": "system", "text": RUNTIME_SYSTEM_PROMPT})
        else:
            payload.append({"role": "system", "text": AGENT_SYSTEM_PROMPT})
        payload.append({"role": "system", "text": extra})
        payload.append({"role": "system", "text": spec_context_block(spec)})
        if mode == "onboarding" and checklist is not None:
            if is_template_agent:
                # Оптимизация #2: компактный контекст для шаблонных агентов —
                # только заполненные поля + dm_send_hint, без 10+ null полей.
                payload.append({"role": "system", "text": _compact_context_block(user, agent, checklist)})
            else:
                payload.append({"role": "system", "text": _context_block(user, agent, checklist, user_text)})
        if runtime_chat_id is not None:
            payload.append({"role": "system", "text": f"current_max_chat_id: {runtime_chat_id}"})
        if tool_trace:
            payload.append(
                {"role": "system", "text": f"tool_results:\n{format_tool_results_for_llm(tool_trace)}"}
            )
        payload.extend(history if mode == "onboarding" else history[-6:])

        await emit_status(status_cb, STATUS_THINKING if iteration == 0 else STATUS_ANALYZING_RESULTS)
        # Runtime-режим с шаблонным промптом (секретарь): ответы короткие, экономим токены
        # При длинном тексте пользователя (инструкция) даём больше токенов на ответ
        if mode == "runtime" and override_system_prompt:
            call_max_tokens = 500
        elif len(user_text or "") > 800:
            call_max_tokens = 3000
        else:
            call_max_tokens = 2000
        raw = await _llm_complete(llm, payload, max_tokens=call_max_tokens)
        data = _parse_llm_json(raw)

        # Отправляем план-рассуждение агента
        if data:
            plan_text = str(data.get("plan") or "").strip()
            if plan_text and reporter_obj is not None:
                await reporter_obj.emit_thinking(plan_text)
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
            # Для шаблонных агентов (secretary и др.) не показываем общий fallback про напоминания
            if override_system_prompt:
                return LlmTurnResult(
                    reply="Не удалось обработать сообщение. Попробуйте сформулировать короче или разбить на части.",
                    checklist=checklist or ChecklistState(),
                ), tool_trace
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
            for call in tool_calls[:8]:
                if not isinstance(call, dict):
                    continue
                tool_name = str(call.get("tool") or "")
                args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                await emit_status(status_cb, tool_status_label(tool_name))
                # Отправляем событие вызова инструмента
                if reporter_obj is not None:
                    await reporter_obj.emit_tool_call(tool_name, args)
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
                # Отправляем краткий результат инструмента
                if reporter_obj is not None:
                    summary = _tool_result_summary(tool_name, result)
                    await reporter_obj.emit_tool_result(tool_name, bool(result.get("ok")), summary)
                if tool_name in {"max_send_file", "max_send_message"} and result.get("ok"):
                    outbound_sent = True
                    attachments = []
                elif tool_name == "max_send_file" and result.get("ok") and isinstance(result.get("result"), dict):
                    att = result["result"].get("attachments")
                    if isinstance(att, list):
                        attachments = att
                # Автоматически переносим bot_is_admin из max_probe_chat в checklist
                if tool_name == "max_probe_chat" and mode == "onboarding" and checklist is not None:
                    bot_is_admin = result.get("bot_is_admin")
                    if bot_is_admin is not None:
                        checklist.bot_is_group_admin = bool(bot_is_admin)
                        logger.info("Auto-set bot_is_group_admin=%s from max_probe_chat", bot_is_admin)
                    # Для шаблонных агентов: probe вызывается один раз — выходим из цикла
                    if is_template_agent and result.get("ok") is not None:
                        outbound_sent = True
                # save_agent_instructions вызывается один раз — после ok прекращаем итерации
                if tool_name == "save_agent_instructions" and result.get("ok") and mode == "onboarding":
                    outbound_sent = True
            if mode == "onboarding" and checklist is not None:
                checklist = _merge_checklist_from_data(data, checklist, user_text, history)
            # В runtime-режиме после отправки сообщения не продолжаем цикл —
            # ждём следующего сообщения от пользователя.
            if mode == "runtime" and outbound_sent:
                return RuntimeLoopResult(text="", attachments=[], outbound_sent=True), tool_trace
            # В onboarding-режиме после сохранения инструкции — выходим из цикла,
            # чтобы LLM не вызывал save_agent_instructions повторно.
            if mode == "onboarding" and outbound_sent:
                reply = str(data.get("reply") or "Инструкция сохранена. Укажите ссылку на группу MAX.").strip()
                return LlmTurnResult(reply=reply, checklist=checklist or ChecklistState()), tool_trace
            continue

        reply = str(data.get("reply") or "").strip()

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


def _compact_context_block(user, agent, checklist) -> str:
    """
    Компактный контекст для шаблонных агентов — только заполненные поля.
    Экономит ~150-200 токенов на каждый LLM-вызов по сравнению с полным _context_block.
    """
    import json as _json
    from app.services.agent.llm_onboarding import checklist_missing_fields

    cfg = dict(agent.config or {})
    lines = [
        f"max_linked: {bool(user.max_user_id)}",
        f"agent_status: {agent.status}",
    ]
    if user.max_user_id:
        lines.append(f"dm_send_hint: max_send_message с user_id={user.max_user_id}")

    # Только заполненные поля чеклиста
    cl_dict = checklist.to_dict()
    filled = {k: v for k, v in cl_dict.items() if v is not None}
    if filled:
        lines.append(f"checklist: {_json.dumps(filled, ensure_ascii=False)}")

    missing = checklist_missing_fields(checklist)
    lines.append(f"missing: {', '.join(missing) if missing else 'нет'}")

    if cfg.get("awaiting_confirmation"):
        lines.append(
            "awaiting_confirmation: true — пользователь уже получил итоговое резюме и ждёт запуска. "
            "Если в его сообщении есть согласие (да, запускай, ок, подтверждаю, верно, go и т.п.) — "
            "немедленно установи activate=true. Не задавай дополнительных вопросов."
        )

    return "\n".join(lines)


def _template_tools_appendix(*, runtime: bool = False) -> str:
    """Appendix для шаблонных агентов — инструменты и формат ответа."""
    if runtime:
        return (
            "Доступные инструменты:\n"
            "- store_agent_record(table, data) — сохранить запись\n"
            "- query_agent_records(table, category=null) — получить записи из БД\n"
            "- delete_agent_record(table, last=false, index=null, match=null) — удалить запись\n"
            "- query_secretary_records(table, category=null, limit=100) — читать записи секретаря группы\n"
            "- max_send_message(chat_id, text) — отправить текст в чат\n"
            "- max_send_file(chat_id, instruction, format) — файл (xlsx/docx/pdf)\n"
            "- read_group_history(chat_id, count=50, from_timestamp=null) — история сообщений группы\n"
            "\n"
            'Формат JSON: {"plan": "кратко", "reply": "...", '
            '"tool_calls": [{"tool": "...", "arguments": {}}]}'
        )
    return (
        'Формат JSON: {"plan": "...", "reply": "...", '
        '"tool_calls": [{"tool": "...", "arguments": {}}], '
        '"checklist": {...}, "ready_for_confirmation": false, "activate": false}'
    )


def _tool_result_summary(tool_name: str, result: dict) -> str:
    """Краткое резюме результата инструмента для отображения пользователю."""
    ok = result.get("ok", False)
    if not ok:
        human = result.get("error_human") or result.get("error") or "ошибка"
        return str(human)[:200]
    r = result.get("result") or {}
    if tool_name == "web_search":
        sources = r.get("sources") or []
        return f"{len(sources)} источников найдено"
    if tool_name in {"max_send_message", "max_send_test"}:
        dest = r.get("chat_id") or r.get("user_id") or ""
        return f"Отправлено{f' в {dest}' if dest else ''}"
    if tool_name == "max_send_file":
        fmt = r.get("format", "")
        dest = r.get("chat_id") or r.get("user_id") or ""
        return f"Файл ({fmt}) отправлен{f' в {dest}' if dest else ''}"
    if tool_name == "max_probe_chat":
        title = r.get("title") or ""
        admin = r.get("bot_is_admin")
        admin_str = " (бот — админ)" if admin is True else " (бот не админ)" if admin is False else ""
        return f"Чат{f' «{title}»' if title else ''}{admin_str}"
    if tool_name == "max_get_chat":
        title = r.get("title") or r.get("chat_id") or ""
        return f"Чат: {title}"
    if tool_name == "max_resolve_channel_link":
        cid = r.get("chat_id") or ""
        title = r.get("title") or ""
        return f"chat_id: {cid}{f' ({title})' if title else ''}"
    if tool_name == "max_list_bot_chats":
        chats = r.get("chats") or []
        return f"{len(chats)} чатов"
    if tool_name == "read_knowledge_base":
        count = r.get("chunk_count") or 0
        return f"{count} фрагментов" if count else "База знаний пуста"
    if tool_name == "update_agent_memory":
        facts = r.get("facts") or []
        return f"Сохранено {len(facts)} фактов"
    if tool_name == "store_agent_record":
        return "Запись сохранена"
    if tool_name == "query_agent_records":
        items = r.get("items") or []
        return f"{len(items)} записей"
    if tool_name == "read_max_api_docs":
        return "Документация прочитана"
    return "ok"


async def _llm_complete(llm, messages: list[dict[str, str]], *, max_tokens: int = 2000) -> str:
    return await llm.complete_text(
        messages, model="pro", max_tokens=max_tokens, temperature=0.35
    )


def _tool_summary(tool_trace: list[dict]) -> str:
    parts = []
    for item in tool_trace[-6:]:
        name = item.get("tool") or "?"
        ok = item.get("ok", False)
        parts.append(f"{name}:{'ok' if ok else 'err'}")
    return ", ".join(parts)
