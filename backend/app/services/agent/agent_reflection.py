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


_REFLECTION_SYSTEM = """Ты проверяешь ответ агента Glosix перед отправкой пользователю.
Верни JSON: {"ok": true/false, "revised_reply": "исправленный ответ или null", "notes": "кратко"}
revised_reply — ТОЛЬКО готовый текст для пользователя на русском. Без инструкций ассистенту,
без «пользователь спрашивает», без названий tools, без «пример ответа», без «ожидайте».
Если нужна только оценка — revised_reply=null, детали в notes.
ok=true если ответ логичен, закрывает задачу, не путает расписание с интерактивным режимом.
ok=false если ответ шаблонный, не по теме, просит расписание там где нужно слушать группу, или противоречит agent_spec.
ok=false если пользователь только спрашивал/проверял (админ, доступ, список чатов), а ответ начал настройку агента
(«Понял задачу», role, «напишите да», просит сделать админом для запуска) без явной просьбы настроить автоматизацию.
ok=false если пользователь просил факт из интернета, а ответ отказывает искать или уходит в настройку автоматизации.
ok=true если ответ даёт факты и источники после web_search."""


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


def should_reflect(*, user_text: str, draft_reply: str, runtime: bool) -> bool:
    """
    Рефлексия только когда есть реальные признаки проблемы.
    Не рефлексируем автоматически — это дополнительный LLM-вызов и задержка.
    """
    body = (draft_reply or "").strip()
    if not body or len(body) < 20:
        return True  # Пустой или подозрительно короткий ответ
    # Ответ выглядит как JSON-структура вместо текста пользователю
    if body.startswith("{") and '"reply"' in body:
        return True
    return False
