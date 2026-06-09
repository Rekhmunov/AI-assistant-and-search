"""Маршрутизация запроса через LLM: выбор потока сервиса без длинных regex-правил."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.models.user import Plan
from app.services.doc_gen_context import refers_to_prior_answer
from app.services.doc_gen_routing import wants_document_generation
from app.services.providers.factory import ChatLLM
from app.services.search_query import normalize_user_query
from app.services.thread_context import ThreadContext, format_history_compact

logger = logging.getLogger(__name__)

ServiceFlow = Literal[
    "search_rag",
    "chat",
    "image_generate",
    "export_chat_document",
]

_FLOW_JSON_RE = re.compile(r"\{[\s\S]*\}")


@dataclass
class LlmFlowDecision:
    flow: ServiceFlow
    needs_search: bool
    answer_model: Literal["lite", "pro"]
    reason: str


_ROUTER_SYSTEM = """Ты маршрутизатор запросов в Glosix (умный ассистент с веб-поиском и файлами).

Верни ТОЛЬКО JSON без markdown:
{
  "flow": "search_rag" | "chat" | "image_generate" | "export_chat_document",
  "needs_search": true/false,
  "answer_model": "lite" | "pro",
  "reason": "кратко по-русски"
}

Возможности сервиса:
- search_rag — нужны свежие данные из интернета, новости, цены, факты с источниками.
- chat — ответ текстом в чате: оферты, договоры, заявления, инструкции, объяснения. Длинные документы ассистент пишет в одном блоке ```markdown … ```. Файлы docx/pdf не создаёт — только текст в чате.
- image_generate — пользователь просит нарисовать/сгенерировать изображение, картинку, логотип.
- export_chat_document — оформить УЖЕ написанный в переписке текст (ответ выше, текст выше, преобразуй в markdown). Не переписывать содержание.

Правила:
- «напиши оферту», «создай договор», «сделай заявление», «сгенерируй документ» → chat (needs_search true если нужны примеры с рынка). answer_model pro для длинных юридических текстов.
- «сгенерируй текст выше в документ», «оформи ответ выше» → export_chat_document, needs_search false.
- Запросы docx/word/pdf/скачать файл как НОВЫЙ документ → chat (markdown в чате), не отдельный файл на сервере.
- При сомнении между chat и search_rag — search_rag если вопрос про актуальные факты.
"""


def _parse_flow_response(raw: str) -> LlmFlowDecision | None:
    text = (raw or "").strip()
    match = _FLOW_JSON_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    flow = str(data.get("flow") or "").strip()
    # legacy: document_file → chat
    if flow == "document_file":
        flow = "chat"
    if flow not in (
        "search_rag",
        "chat",
        "image_generate",
        "export_chat_document",
    ):
        return None
    needs_search = bool(data.get("needs_search"))
    model = str(data.get("answer_model") or "lite").strip()
    if model not in ("lite", "pro"):
        model = "lite"
    reason = str(data.get("reason") or "llm_router")[:200]
    return LlmFlowDecision(
        flow=flow,  # type: ignore[arg-type]
        needs_search=needs_search,
        answer_model=model,  # type: ignore[arg-type]
        reason=reason,
    )


def _normalize_flow(query: str, decision: LlmFlowDecision, user_plan: Plan) -> LlmFlowDecision:
    q = normalize_user_query(query)

    if wants_document_generation(q) and not refers_to_prior_answer(q):
        return LlmFlowDecision(
            flow="chat",
            needs_search=decision.needs_search,
            answer_model="pro" if user_plan == Plan.PRO else "lite",
            reason="document_markdown_chat",
        )

    if refers_to_prior_answer(q):
        return LlmFlowDecision(
            flow="export_chat_document",
            needs_search=False,
            answer_model="lite",
            reason="export_prior_markdown",
        )

    if decision.flow == "export_chat_document" and not refers_to_prior_answer(q):
        return LlmFlowDecision(
            flow="chat",
            needs_search=decision.needs_search,
            answer_model=decision.answer_model,
            reason="export_misroute_to_chat",
        )

    return decision


async def resolve_service_flow(
    llm: ChatLLM,
    query: str,
    ctx: ThreadContext,
    *,
    has_attachments: bool,
    user_plan: Plan,
) -> LlmFlowDecision:
    """LLM выбирает поток; при ошибке — безопасный search_rag."""
    if has_attachments:
        return LlmFlowDecision(
            flow="search_rag",
            needs_search=True,
            answer_model="pro" if user_plan == Plan.PRO else "lite",
            reason="attachments",
        )

    q = normalize_user_query(query)
    history = format_history_compact(ctx.history, max_turns=3, max_chars=400)
    user_block = f"Запрос пользователя:\n{q}"
    if history:
        user_block += f"\n\nКонтекст треда:\n{history}"
    if ctx.is_continuation:
        user_block += "\n(есть предыдущие сообщения в треде)"

    messages = [
        {"role": "system", "text": _ROUTER_SYSTEM},
        {"role": "user", "text": user_block},
    ]
    try:
        raw = await llm.complete_text(
            messages,
            model="lite",
            max_tokens=256,
            temperature=0.0,
        )
        parsed = _parse_flow_response(raw)
        if parsed:
            parsed = _normalize_flow(q, parsed, user_plan)
            if user_plan != Plan.PRO:
                parsed.answer_model = "lite"
            return parsed
    except Exception:
        logger.exception("llm flow router failed")

    fallback = LlmFlowDecision(
        flow="search_rag",
        needs_search=True,
        answer_model="lite",
        reason="llm_router_fallback",
    )
    return _normalize_flow(q, fallback, user_plan)
