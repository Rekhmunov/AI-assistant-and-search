"""Маршрутизация запроса через LLM: выбор потока сервиса без длинных regex-правил."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.models.user import Plan
from app.services.providers.factory import ChatLLM
from app.services.search_query import normalize_user_query
from app.services.thread_context import ThreadContext, format_history_compact

logger = logging.getLogger(__name__)

ServiceFlow = Literal[
    "search_rag",
    "chat",
    "image_generate",
    "document_file",
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
  "flow": "search_rag" | "chat" | "image_generate" | "document_file" | "export_chat_document",
  "needs_search": true/false,
  "answer_model": "lite" | "pro",
  "reason": "кратко по-русски"
}

Возможности сервиса:
- search_rag — нужны свежие данные из интернета, новости, цены, факты с источниками.
- chat — ответ текстом в чате: оферты, договоры, инструкции, объяснения. Длинные документы ассистент пишет в markdown-блоке. Не создаёт файл.
- image_generate — пользователь просит нарисовать/сгенерировать изображение, картинку, логотип.
- document_file — нужен новый файл Word (.docx) с нуля: явно просят «файл», «документ docx», «скачать заявление» как файл, без опоры на готовый текст выше.
- export_chat_document — оформить/скачать УЖЕ написанный в переписке текст (ответ выше, текст выше, в docx, преобразуй в документ). Не переписывать содержание.

Правила:
- «напиши в чат оферту», «сформируй оферту» → chat (needs_search true если нужны примеры с рынка).
- «сгенерируй текст выше в документ», «оформи ответ в word» → export_chat_document, needs_search false.
- «сделай заявление на отпуск» без слова файл/документ → chat, не document_file.
- «создай документ договор» / «скачай docx заявления» → document_file.
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
    if flow not in (
        "search_rag",
        "chat",
        "image_generate",
        "document_file",
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
            if user_plan != Plan.PRO:
                parsed.answer_model = "lite"
            return parsed
    except Exception:
        logger.exception("llm flow router failed")

    return LlmFlowDecision(
        flow="search_rag",
        needs_search=True,
        answer_model="lite",
        reason="llm_router_fallback",
    )
