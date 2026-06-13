"""Рефлексия: проверка ответа перед отправкой пользователю."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    ok: bool
    revised_reply: str | None
    notes: str = ""


_REFLECTION_SYSTEM = """Ты проверяешь завершённость задачи в ответе агента Glosix.
Верни JSON: {"ok": true/false, "revised_reply": "исправленный ответ или null", "notes": "кратко"}
revised_reply — ТОЛЬКО готовый текст для пользователя на русском, без служебных инструкций и названий tools.
Если нужна только оценка — revised_reply=null.

ГЛАВНЫЙ КРИТЕРИЙ — задача пользователя на этом шаге выполнена?

ok=false если:
• Инструмент вернул результат, но ответ его игнорирует
• Ответ обещает действие без реального вызова инструмента
• Ответ не отвечает на заданный вопрос пользователя
• Ответ уходит от темы без возврата

ok=true если:
• Ответ закрывает текущий шаг (вопрос задан, параметр записан, итог показан)
• Действие совершено и подтверждено
• Уточнение получено и обработано"""


async def critique_agent_reply(
    llm,
    *,
    user_text: str,
    draft_reply: str,
    spec_context: str,
    answer_model: str = "pro",
) -> ReflectionResult:
    if not (draft_reply or "").strip():
        return ReflectionResult(ok=False, revised_reply="Не удалось сформировать ответ.", notes="empty")

    messages = [
        {"role": "system", "text": _REFLECTION_SYSTEM},
        {
            "role": "user",
            "text": (
                f"agent_spec:\n{spec_context[:3500]}\n\n"
                f"Вопрос пользователя:\n{user_text[:1500]}\n\n"
                f"Черновик ответа:\n{draft_reply[:2000]}"
            ),
        },
    ]
    try:
        raw = await llm.complete_text(
            messages,
            model="pro" if answer_model == "pro" else "lite",
            max_tokens=700,
            temperature=0.15,
        )
    except Exception as exc:
        logger.warning("Reflection LLM failed: %s", exc)
        return ReflectionResult(ok=True, revised_reply=None, notes="reflection_skipped")

    data = _parse_json(raw)
    if not data:
        return ReflectionResult(ok=True, revised_reply=None, notes="reflection_parse_failed")

    ok = bool(data.get("ok", True))
    revised = data.get("revised_reply")
    notes = str(data.get("notes") or "")
    if isinstance(revised, str) and revised.strip():
        from app.services.agent.agent_reply_sanitize import sanitize_user_facing_reply

        clean = sanitize_user_facing_reply(revised)
        if clean:
            return ReflectionResult(ok=ok, revised_reply=clean, notes=notes)
        return ReflectionResult(ok=ok, revised_reply=None, notes=notes or "meta_reply_discarded")
    return ReflectionResult(ok=ok, revised_reply=None, notes=notes)


def _parse_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    end = text.rfind("}")
    if end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def should_reflect(
    *,
    user_text: str,
    draft_reply: str,
    runtime: bool,
    tool_trace: list | None = None,
) -> bool:
    """
    Проверяем завершённость задачи, не просто непустоту ответа.
    Рефлексия — это дополнительный LLM-вызов, используем точечно.
    """
    body = (draft_reply or "").strip()

    # Явно плохой ответ
    if not body or len(body) < 20:
        return True
    if body.startswith("{") and '"reply"' in body:
        return True

    # Успешные tool-вызовы были, но ответ слишком короткий
    # (вероятно, не использует результаты)
    if tool_trace:
        successful = [t for t in tool_trace if isinstance(t, dict) and t.get("ok")]
        if successful and len(body) < 60:
            return True

    return False
