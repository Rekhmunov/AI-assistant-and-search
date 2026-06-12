"""Обратная связь пользователю после tool-вызовов агента."""

from __future__ import annotations

from typing import Any


def summarize_tool_trace_for_user(tool_trace: list[dict]) -> str | None:
    """Краткая сводка по результатам tool-вызовов — используется только как fallback при пустом ответе LLM."""
    if not tool_trace:
        return None
    lines: list[str] = []
    for item in tool_trace:
        if not isinstance(item, dict):
            continue
        if not item.get("ok"):
            msg = item.get("error_human") or item.get("error") or "ошибка"
            lines.append(f"Не удалось: {msg}")
        else:
            result = item.get("result") or {}
            tool = str(item.get("tool") or "")
            if tool == "max_send_message":
                chat_id = result.get("chat_id")
                user_id = result.get("user_id")
                dest = f" в группу {chat_id}" if chat_id else (f" пользователю {user_id}" if user_id else "")
                lines.append(f"Сообщение отправлено{dest}.")
            elif tool == "max_probe_chat":
                explanation = str(result.get("explanation") or "").strip()
                if explanation:
                    lines.append(explanation)
            elif tool == "web_search":
                text = str(result.get("text") or "").strip()
                if text:
                    lines.append(text[:800])
    if not lines:
        return "Готово."
    return "\n\n".join(lines)


def ensure_action_feedback(reply: str, tool_trace: list[dict], user_text: str) -> str:
    """
    Возвращает ответ пользователю.
    Доверяем LLM — заменяем только если ответ полностью пустой.
    """
    from app.services.agent.agent_reply_sanitize import sanitize_user_facing_reply

    body = sanitize_user_facing_reply(reply)
    if body:
        return body

    # Ответ пустой — используем сводку из tool_trace
    summary = summarize_tool_trace_for_user(tool_trace)
    if summary:
        return summary

    return "Не удалось сформировать ответ. Попробуйте переформулировать запрос."


# Нудж для loop: LLM пообещал действие, но tool не вызвал
PROMISE_WITHOUT_TOOLS_NUDGE = (
    "Вызови tools для действия в MAX, затем reply с фактическим итогом для пользователя."
)


def reply_is_deferred_promise(reply: str) -> bool:
    """Устарел — больше не используется для замены reply."""
    return False


def user_expects_immediate_max_action(user_text: str) -> bool:
    """Устарел."""
    return False
