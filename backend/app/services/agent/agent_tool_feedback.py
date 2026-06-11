"""Гарантированная обратная связь пользователю после tool-вызовов агента."""

from __future__ import annotations

import re
from typing import Any

from app.services.agent.operational import _has_write_to_group_intent

_DEFERRED_PROMISE_RE = re.compile(
    r"(?:"
    r"проверю|проверяю|сейчас\s+провер|отправлю|отправляю|сейчас\s+отправ|"
    r"повторно\s+отправ|сделаю\s+это|сейчас\s+сделаю|подожди|подождите|"
    r"дай(?:те)?\s+(?:мне\s+)?(?:секунд|минут)|одну\s+минут"
    r")",
    re.I,
)

_OUTCOME_RE = re.compile(
    r"(?:"
    r"\bотправлен\w*|\bдоставлен\w*|не\s+удалось|ошибк|\bготов[оа]\b|\bсделан\w*|"
    r"бот\s+—\s+админ|является\s+админ|не\s+админ|связь\s+с\s+чатом|"
    r"сообщение\s+отправлен|отправлено\s+в\s+max|результат\s+проверк"
    r")",
    re.I,
)


def reply_is_deferred_promise(reply: str) -> bool:
    text = (reply or "").strip()
    if len(text) < 8:
        return False
    if _OUTCOME_RE.search(text):
        return False
    return bool(_DEFERRED_PROMISE_RE.search(text))


def reply_reports_tool_outcome(reply: str) -> bool:
    return bool(_OUTCOME_RE.search(reply or ""))


def user_expects_immediate_max_action(user_text: str) -> bool:
    low = (user_text or "").lower()
    if _has_write_to_group_intent(low):
        return True
    if re.search(r"провер\w*", low) and re.search(r"чат|групп|max|бот", low):
        return True
    return False


def _summarize_tool_item(item: dict[str, Any]) -> str | None:
    tool = str(item.get("tool") or "").strip().lower()
    if not tool:
        return None
    if not item.get("ok"):
        err = str(item.get("error") or "неизвестная ошибка").strip()
        return f"Не удалось выполнить «{tool}»: {err}"

    result = item.get("result")
    if not isinstance(result, dict):
        return None

    if tool == "max_probe_chat":
        explanation = str(result.get("explanation") or "").strip()
        if explanation:
            return explanation
        title = str(result.get("title") or "").strip()
        admin = result.get("bot_is_admin")
        if admin is True:
            return f"Бот имеет доступ к группе{f' «{title}»' if title else ''} и является администратором."
        if admin is False:
            return f"Бот в группе{f' «{title}»' if title else ''}, но не администратор."
        return "Проверка доступа бота к группе MAX завершена."

    if tool == "max_send_message":
        if result.get("error"):
            return f"Не удалось отправить сообщение в MAX: {result['error']}"
        chat_id = result.get("chat_id")
        return f"Сообщение отправлено в MAX{f' (группа {chat_id})' if chat_id else ''}."

    if tool == "max_send_test":
        explanation = str(result.get("explanation") or "").strip()
        return explanation or "Тестовое сообщение отправлено в MAX."

    if tool == "max_get_chat":
        title = str(result.get("title") or "чат").strip()
        status = str(result.get("status") or "").strip()
        if status:
            return f"Чат MAX «{title}», статус бота: {status}."
        return f"Данные чата MAX: «{title}»."

    if tool == "max_resolve_channel_link":
        chat_id = result.get("chat_id")
        title = str(result.get("title") or "").strip()
        if chat_id:
            return f"Группа найдена: «{title or chat_id}» (ID {chat_id})."
        return None

    if tool == "web_search":
        text = str(result.get("text") or "").strip()
        return text[:1200] if text else None

    return None


def summarize_tool_trace_for_user(tool_trace: list[dict]) -> str | None:
    if not tool_trace:
        return None
    lines: list[str] = []
    for item in tool_trace:
        if not isinstance(item, dict):
            continue
        line = _summarize_tool_item(item)
        if line and line not in lines:
            lines.append(line)
    if not lines:
        failed = [it for it in tool_trace if isinstance(it, dict) and not it.get("ok")]
        if failed:
            err = str(failed[-1].get("error") or "ошибка").strip()
            return f"Действие не выполнено: {err}"
        return "Готово."
    return "\n\n".join(lines)


def ensure_action_feedback(reply: str, tool_trace: list[dict], user_text: str) -> str:
    from app.services.agent.agent_reply_sanitize import sanitize_user_facing_reply
    """
    Пользователь всегда получает итог: либо ответ модели с результатом,
    либо сводку по tool_trace, либо явное сообщение об ошибке.
    """
    body = sanitize_user_facing_reply(reply)
    summary = summarize_tool_trace_for_user(tool_trace)

    if tool_trace:
        if not body or reply_is_deferred_promise(body) or not reply_reports_tool_outcome(body):
            if summary:
                return summary
        if summary and not reply_reports_tool_outcome(body):
            return f"{body}\n\n{summary}".strip()
        return body or summary or "Готово."

    if body and reply_is_deferred_promise(body) and user_expects_immediate_max_action(user_text):
        return (
            "Не удалось завершить действие: агент не выполнил проверку или отправку в MAX. "
            "Укажите ссылку на группу (web.max.ru/-ID) или ID чата и повторите запрос."
        )

    return body or "Не удалось сформировать ответ. Попробуйте переформулировать запрос."


PROMISE_WITHOUT_TOOLS_NUDGE = (
    "Вызови tools для действия в MAX, затем reply с фактическим итогом для пользователя."
)
